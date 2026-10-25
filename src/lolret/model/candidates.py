"""Candidate features (ADR 0013): LightGBM on the 21 features plus the candidates.

The candidates live in `candidates.parquet`, apart from `FEATURES`, until the forward test
decides whether they join the model. The model follows the ladder's LightGBM protocol
(ADR 0008): rounds by early stopping on the player-grouped folds, Platt scaling on the
out-of-fold predictions, the same parameters.

`evaluate_candidates` compares it with the ladder's LightGBM on the 4a test set, for the
record only: that test set already judged four of these features (ADR 0010).
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

import duckdb
import numpy as np

from lolret.model.config import TrainConfig
from lolret.model.data import (
    FEATURES,
    Examples,
    Labels,
    Matrix,
    Vector,
    load_examples,
    split_by_player_and_time,
)
from lolret.model.evaluate import evaluate
from lolret.model.models import GBM, Ladder, Platt, cv_lightgbm, player_folds
from lolret.model.train import examples_path, models_dir

CANDIDATES: tuple[str, ...] = (
    "returns_8w",
    "longest_gap_days",
    "break_vs_longest_gap",
    "summoner_level",
    "repeated_teammates",
)
NAMES = (*FEATURES, *CANDIDATES)
MODEL = "lightgbm_candidates"
RESULTS_FILE = "candidates.json"


def candidates_path(data_dir: Path, dataset: str) -> Path:
    return data_dir / "processed" / dataset / "candidates.parquet"


def load_candidates(path: Path, examples: Examples) -> Matrix:
    """The candidate columns for every example, in the order of `examples` (NaN if NULL)."""
    columns = ", ".join(f"coalesce({c}::DOUBLE, 'NaN'::DOUBLE) AS {c}" for c in CANDIDATES)
    # Column names come from CANDIDATES, a constant in this module, not from user input.
    query = (
        f"SELECT platform || ':' || puuid AS player, cutoff, {columns} "  # noqa: S608
        "FROM read_parquet(?)"
    )
    with duckdb.connect() as con:
        c = con.execute(query, [str(path)]).fetchnumpy()
    seconds = np.asarray(c["cutoff"]).astype("datetime64[s]").astype(np.int64)
    stored = zip(np.asarray(c["player"]).tolist(), seconds.tolist(), strict=True)
    row = {k: i for i, k in enumerate(stored)}
    keys = zip(
        examples.player.tolist(),
        examples.cutoff.astype("datetime64[s]").astype(np.int64).tolist(),
        strict=True,
    )
    idx = np.array([row[k] for k in keys], dtype=np.int64)
    return np.column_stack([np.asarray(c[name], dtype=np.float64)[idx] for name in CANDIDATES])


@dataclass(frozen=True)
class CandidateGBM:
    gbm: GBM
    platt: Platt
    rounds: int

    @classmethod
    def fit(cls, x: Matrix, y: Labels, players: np.ndarray, cfg: TrainConfig) -> Self:
        """`x` holds `FEATURES` then `CANDIDATES`."""
        folds = player_folds(players, cfg.cv_folds, cfg.seed)
        oof, rounds = cv_lightgbm(x, y, folds, cfg.lightgbm, cfg.seed, names=NAMES)
        gbm = GBM.fit(x, y, cfg.lightgbm, rounds, cfg.seed, names=NAMES)
        return cls(gbm, Platt.fit(oof, y), rounds)

    def predict(self, x: Matrix) -> Vector:
        return self.platt.apply(self.gbm.predict(x))


def with_candidates(examples: Examples, path: Path) -> Matrix:
    return np.hstack([examples.x, load_candidates(path, examples)])


def evaluate_candidates(cfg: TrainConfig, data_dir: Path) -> dict[str, Any]:
    """Fit on the 4a training set, compare with the ladder on the 4a test set, and write
    `candidates.json` next to the ladder."""
    model_dir = models_dir(data_dir, cfg.dataset)
    if not (model_dir / "models.json").exists():
        raise FileNotFoundError(f"no classical models in {model_dir}: run `lolret train` first")
    source = candidates_path(data_dir, cfg.dataset)
    train, test = split_by_player_and_time(
        load_examples(examples_path(data_dir, cfg.dataset)), cfg.test_fraction, cfg.seed
    )
    model = CandidateGBM.fit(with_candidates(train, source), train.y, train.player, cfg)
    preds = Ladder.load(model_dir).predict(test.x)
    preds[MODEL] = model.predict(with_candidates(test, source))
    common = {"n_boot": cfg.bootstrap, "seed": cfg.seed}
    results, vs_recency = evaluate(test.y, preds, baseline="recency", **common)
    _, vs_lightgbm = evaluate(test.y, preds, baseline="lightgbm", **common)
    summary = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "candidates": list(CANDIDATES),
        "rounds": model.rounds,
        "test": {name: results[name] for name in ("recency", "lightgbm", MODEL)},
        "vs_recency": vs_recency[MODEL],
        "vs_lightgbm": vs_lightgbm[MODEL],
    }
    (model_dir / RESULTS_FILE).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
