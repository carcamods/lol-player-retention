"""Train the classical ladder on a built dataset and evaluate it on the held-out test set.

Output, in `data/models/<dataset>/`:
- `models.json` and `lightgbm.txt`: the fitted models (see `models.py`).
- `metrics.json`: data sizes, model selection, test metrics with bootstrap intervals,
  reliability bins and feature importance.
- `model_card.md`: the same, written for people.

Nothing written here identifies a player.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from lolret import __version__
from lolret.log import get_logger
from lolret.model.card import render_model_card
from lolret.model.config import TrainConfig
from lolret.model.data import Examples, load_examples, split_by_player_and_time
from lolret.model.evaluate import brier, evaluate, lightgbm_importance, reliability
from lolret.model.models import (
    GBM,
    Ladder,
    LogReg,
    Majority,
    Platt,
    Recency,
    cv_lightgbm,
    player_folds,
    select_logreg,
)

log = get_logger(__name__)

BASELINE = "recency"
METRICS_FILE = "metrics.json"
CARD_FILE = "model_card.md"
FEW_TEST_POSITIVES = 100  # below this, warn that the intervals will be wide


class InsufficientDataError(ValueError):
    """Too few examples, players or churners to train or to evaluate."""


@dataclass(frozen=True)
class TrainSummary:
    out_dir: Path
    train_rows: int
    test_rows: int
    test_positives: int
    test: dict[str, dict[str, Any]]  # metrics per model, as in metrics.json


def examples_path(data_dir: Path, dataset: str) -> Path:
    return data_dir / "processed" / dataset / "examples.parquet"


def models_dir(data_dir: Path, dataset: str) -> Path:
    return data_dir / "models" / dataset


def _check_sizes(train: Examples, test: Examples, cv_folds: int) -> None:
    train_pos = int(train.y.sum())
    need = 2 * cv_folds
    if len(np.unique(train.player)) < cv_folds or min(train_pos, len(train) - train_pos) < need:
        raise InsufficientDataError(
            f"training set has {len(train)} examples and {train_pos} churners; cross-validation "
            f"with {cv_folds} folds needs at least {need} of each class"
        )
    test_pos = int(test.y.sum())
    if not 0 < test_pos < len(test):
        raise InsufficientDataError(
            f"test set has {len(test)} examples and {test_pos} churners; it needs both classes"
        )


def _describe(examples: Examples) -> dict[str, Any]:
    return {
        "examples": len(examples),
        "players": len(np.unique(examples.player)),
        "churned": int(examples.y.sum()),
        "churn_rate": float(examples.y.mean()),
        "cutoffs": sorted({str(c)[:10] for c in examples.cutoff}),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def train_and_evaluate(cfg: TrainConfig, data_dir: Path) -> TrainSummary:
    source = examples_path(data_dir, cfg.dataset)
    train, test = split_by_player_and_time(load_examples(source), cfg.test_fraction, cfg.seed)
    _check_sizes(train, test, cfg.cv_folds)
    log.info(
        "Train: %d examples, %d players. Test: %d examples, %d churned.",
        len(train),
        len(np.unique(train.player)),
        len(test),
        int(test.y.sum()),
    )
    if test.y.sum() < FEW_TEST_POSITIVES:
        log.warning(
            "Only %d churned players in the test set: the intervals will be wide.",
            int(test.y.sum()),
        )

    folds = player_folds(train.player, cfg.cv_folds, cfg.seed)
    c, logreg_oof, cv_log_loss = select_logreg(train.x, train.y, folds, cfg.logreg_c)
    gbm_oof, rounds = cv_lightgbm(train.x, train.y, folds, cfg.lightgbm, cfg.seed)
    log.info("Selected logistic regression C=%s and %d LightGBM rounds.", c, rounds)
    ladder = Ladder(
        majority=Majority.fit(train.y),
        recency=Recency.fit(train.x, train.y),
        logreg=LogReg.fit(train.x, train.y, c),
        logreg_platt=Platt.fit(logreg_oof, train.y),
        lightgbm=GBM.fit(train.x, train.y, cfg.lightgbm, rounds, cfg.seed),
        lightgbm_platt=Platt.fit(gbm_oof, train.y),
    )

    preds = ladder.predict(test.x)
    results, vs_baseline = evaluate(
        test.y, preds, baseline=BASELINE, n_boot=cfg.bootstrap, seed=cfg.seed
    )
    results["logreg"]["brier_uncalibrated"] = brier(test.y, ladder.logreg.predict(test.x))
    results["lightgbm"]["brier_uncalibrated"] = brier(test.y, ladder.lightgbm.predict(test.x))

    metrics: dict[str, Any] = {
        "dataset": cfg.dataset,
        "examples_sha256": _sha256(source),
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "lolret_version": __version__,
        "config": cfg.model_dump(),
        "data": {"train": _describe(train), "test": _describe(test)},
        "selection": {
            "logreg_c": c,
            "logreg_cv_log_loss": cv_log_loss,
            "lightgbm_rounds": rounds,
            "platt": {
                "logreg": [ladder.logreg_platt.a, ladder.logreg_platt.b],
                "lightgbm": [ladder.lightgbm_platt.a, ladder.lightgbm_platt.b],
            },
        },
        "baseline": BASELINE,
        "test": results,
        "vs_baseline": vs_baseline,
        "reliability": {name: reliability(test.y, p) for name, p in preds.items()},
        "importance": {
            "lightgbm_mean_abs_shap": lightgbm_importance(ladder.lightgbm.booster, test.x),
            "logreg_coef": dict(
                sorted(
                    zip(ladder.logreg.design_names(), ladder.logreg.coef, strict=True),
                    key=lambda kv: -abs(kv[1]),
                )
            ),
        },
    }

    out_dir = models_dir(data_dir, cfg.dataset)
    ladder.save(out_dir)
    (out_dir / METRICS_FILE).write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (out_dir / CARD_FILE).write_text(render_model_card(metrics), encoding="utf-8")
    return TrainSummary(
        out_dir=out_dir,
        train_rows=len(train),
        test_rows=len(test),
        test_positives=int(test.y.sum()),
        test=results,
    )
