"""The Bronze expansion (ADR 0015): does a Bronze-only model beat the general one with more data?

Run `bronze` samples 464 players per Bronze division, and its first 72 per division are v1's.
The examples join both runs, with v1's rows for v1's players. Two LightGBM models follow the
ladder's protocol (ADR 0008) on the players who are not held out, at the earlier cutoffs:
`general` on every tier, `bronze_only` on the Bronze rows of the same set.

The rule, written before collecting, is judged on the fresh Bronze test players: held out by
the usual hash, new in `bronze` (the 4a evaluation already looked at v1's), at the latest cutoff.

1. `bronze_only` against `general`: Bronze gets its own model only if the 95% interval of the
   paired PR-AUC difference is above zero. Otherwise the general model stays.
2. The kept model against the recency rule, the same way.

EUW alone and a Bronze learning curve are reported, not decided on.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

import duckdb
import numpy as np
from numpy.typing import NDArray

from lolret.model.config import TrainConfig
from lolret.model.data import FEATURES, Examples, Matrix, Vector, in_test_set, load_examples
from lolret.model.evaluate import evaluate, scores
from lolret.model.models import GBM, Platt, Recency, cv_lightgbm, player_folds
from lolret.model.train import describe, examples_path, models_dir, sha256

RUN = "bronze"
BRONZE = "BRONZE"
EUW = "euw1"
RECENCY, GENERAL, BRONZE_ONLY = "recency", "general", "bronze_only"
RESULTS_FILE = "evaluation.json"
CURVE = (0.0625, 0.125, 0.25, 0.5, 1.0)  # shares of the Bronze training players
CURVE_REPEATS = 3  # random player subsets per share below 1


@dataclass(frozen=True)
class LightGBM:
    """The ladder's LightGBM: rounds by early stopping on player-grouped folds, Platt scaling
    on the out-of-fold predictions."""

    gbm: GBM
    platt: Platt
    rounds: int

    @classmethod
    def fit(cls, train: Examples, cfg: TrainConfig) -> Self:
        folds = player_folds(train.player, cfg.cv_folds, cfg.seed)
        oof, rounds = cv_lightgbm(train.x, train.y, folds, cfg.lightgbm, cfg.seed)
        gbm = GBM.fit(train.x, train.y, cfg.lightgbm, rounds, cfg.seed)
        return cls(gbm, Platt.fit(oof, train.y), rounds)

    def predict(self, x: Matrix) -> Vector:
        return self.platt.apply(self.gbm.predict(x))


def combine(base: Examples, run: Examples) -> tuple[Examples, NDArray[np.bool_]]:
    """`base`'s rows plus `run`'s rows of players not in `base`, and which rows are new."""
    extra = run.subset(~np.isin(run.player, base.player))
    examples = Examples(
        x=np.vstack([base.x, extra.x]),
        y=np.concatenate([base.y, extra.y]),
        player=np.concatenate([base.player, extra.player]),
        cutoff=np.concatenate([base.cutoff, extra.cutoff]),
    )
    new = np.concatenate([np.zeros(len(base), np.bool_), np.ones(len(extra), np.bool_)])
    return examples, new


def overlap(base: Examples, run: Examples) -> dict[str, Any]:
    """The players both runs hold, and whether their rows match beyond float rounding.

    They read the same cached responses, but a run that caches more match details (fetched for
    other players in the same games) can shift a feature that looks past the 20 recent games.
    """
    shared = np.intersect1d(base.player, run.player)
    a, b = base.subset(np.isin(base.player, shared)), run.subset(np.isin(run.player, shared))
    aligned = (
        len(a) == len(b)
        and bool((a.player == b.player).all())
        and bool((a.cutoff == b.cutoff).all())
    )
    if not aligned:
        return {"players": len(shared), "rows_aligned": False}
    close = np.isclose(a.x, b.x, rtol=1e-9, atol=0.0, equal_nan=True)
    return {
        "players": len(shared),
        "rows_aligned": True,
        "labels_identical": bool((a.y == b.y).all()),
        "features_differing": {
            name: int((~close[:, i]).sum())
            for i, name in enumerate(FEATURES)
            if not close[:, i].all()
        },
    }


def tiers(*paths: Path) -> dict[str, str]:
    """Each player's ladder tier (metadata, never a feature) from the runs' examples."""
    out: dict[str, str] = {}
    with duckdb.connect() as con:
        for path in paths:
            rows = con.execute(
                "SELECT DISTINCT platform || ':' || puuid, tier FROM read_parquet(?)", [str(path)]
            ).fetchall()
            out |= dict(rows)
    return out


def above_zero(comparison: dict[str, Any]) -> bool:
    ci = comparison["pr_auc_diff_ci"]
    return ci is not None and ci[0] > 0


def judge(y: NDArray[np.int64], preds: dict[str, Vector], cfg: TrainConfig) -> dict[str, Any]:
    """ADR 0015's two steps on one set of test players, on the same bootstrap resamples."""
    common = {"n_boot": cfg.bootstrap, "seed": cfg.seed}
    results, vs_general = evaluate(y, preds, baseline=GENERAL, **common)
    _, vs_recency = evaluate(y, preds, baseline=RECENCY, **common)
    own_model = above_zero(vs_general[BRONZE_ONLY])
    kept = BRONZE_ONLY if own_model else GENERAL
    return {
        "examples": len(y),
        "churned": int(y.sum()),
        "test": results,
        "bronze_only_vs_general": vs_general[BRONZE_ONLY],
        "vs_recency": {name: vs_recency[name] for name in (GENERAL, BRONZE_ONLY)},
        "bronze_gets_own_model": own_model,
        "kept": kept,
        "kept_beats_recency": above_zero(vs_recency[kept]),
    }


def learning_curve(
    train: Examples, test: Examples, cfg: TrainConfig, shares: tuple[float, ...]
) -> list[dict[str, Any]]:
    """Bronze-only PR-AUC on the fresh test players, by share of the Bronze training players.

    Reporting only: nothing is chosen from it.
    """
    players = np.unique(train.player)
    rng = np.random.default_rng(cfg.seed)
    points: list[dict[str, Any]] = []
    for share in shares:
        n = max(round(share * len(players)), cfg.cv_folds)
        runs: list[float] = []
        sizes: list[int] = []
        for _ in range(1 if n >= len(players) else CURVE_REPEATS):
            subset = train.subset(np.isin(train.player, rng.choice(players, n, replace=False)))
            pr_auc = scores(test.y, LightGBM.fit(subset, cfg).predict(test.x))["pr_auc"]
            runs.append(float("nan") if pr_auc is None else pr_auc)
            sizes.append(len(subset))
        points.append(
            {
                "share": share,
                "players": n,
                "examples": round(float(np.mean(sizes))),
                "pr_auc": float(np.mean(runs)),
                "pr_auc_runs": runs,
            }
        )
    return points


def evaluate_bronze(
    cfg: TrainConfig, data_dir: Path, run: str = RUN, curve: tuple[float, ...] = CURVE
) -> dict[str, Any]:
    """Fit both models, judge them by ADR 0015's rule, and write `evaluation.json` in
    `data/models/<run>/`."""
    base_path, run_path = examples_path(data_dir, cfg.dataset), examples_path(data_dir, run)
    for path in (base_path, run_path):
        if not path.exists():
            raise FileNotFoundError(f"no dataset at {path}: run `lolret build` first")
    base, extra = load_examples(base_path), load_examples(run_path)
    examples, new = combine(base, extra)
    tier = tiers(base_path, run_path)
    bronze = np.array([tier[p] == BRONZE for p in examples.player.tolist()], dtype=np.bool_)
    held_out = np.array(
        [in_test_set(p, cfg.test_fraction, cfg.seed) for p in examples.player.tolist()],
        dtype=np.bool_,
    )
    latest = examples.cutoff.max()
    in_train = ~held_out & (examples.cutoff < latest)
    train, bronze_train = examples.subset(in_train), examples.subset(in_train & bronze)
    test = examples.subset(held_out & (examples.cutoff == latest) & new & bronze)

    general, bronze_only = LightGBM.fit(train, cfg), LightGBM.fit(bronze_train, cfg)
    preds = {
        RECENCY: Recency.fit(train.x, train.y).predict(test.x),
        GENERAL: general.predict(test.x),
        BRONZE_ONLY: bronze_only.predict(test.x),
    }
    euw = np.char.startswith(test.player, f"{EUW}:")
    summary = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "runs": [cfg.dataset, run],
        "examples_sha256": {cfg.dataset: sha256(base_path), run: sha256(run_path)},
        "overlap": overlap(base, extra),
        "data": {
            "train": describe(train),
            "train_bronze": describe(bronze_train),
            "test": describe(test),
        },
        "rounds": {GENERAL: general.rounds, BRONZE_ONLY: bronze_only.rounds},
        "rule": judge(test.y, preds, cfg),
        "euw": judge(test.y[euw], {name: p[euw] for name, p in preds.items()}, cfg),
        "learning_curve": learning_curve(bronze_train, test, cfg, curve),
    }
    out_dir = models_dir(data_dir, run)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / RESULTS_FILE).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
