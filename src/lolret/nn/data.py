"""Inputs for the neural nets: the tabular features and each example's recent-match sequence.

`sequences.parquet` (from `lolret build`) holds the 20 most recent games that ended before each
cutoff. They are laid out oldest first, so a GRU's last state follows the newest game.
Standardisation statistics come from the training rows only, like the logistic regression's.
"""

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import duckdb
import numpy as np
from numpy.typing import NDArray

from lolret.model.data import Examples, Matrix
from lolret.model.models import signed_log1p

SEQ_LEN = 20
QUEUES = (420, 440, 450)  # ranked solo, ranked flex, ARAM; anything else is "other"
ROLES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")  # or none (ARAM, arena...)
STEP_FEATURES: tuple[str, ...] = (
    "log_hours_before_cutoff",
    "log_gap_hours",
    "gap_missing",
    "duration_30min",
    "win",
    "log_kills",
    "log_deaths",
    "log_assists",
    "remake",
    "surrendered",
    *(f"queue_{q}" for q in QUEUES),
    "queue_other",
    *(f"role_{r.lower()}" for r in ROLES),
    "role_none",
    "same_champion",
)

Sequences = NDArray[np.float32]  # (examples, SEQ_LEN, len(STEP_FEATURES)), oldest game first
Lengths = NDArray[np.int64]  # games per example, 0 to SEQ_LEN


def sequences_path(data_dir: Path, dataset: str) -> Path:
    return data_dir / "processed" / dataset / "sequences.parquet"


def _seconds(values: Any) -> NDArray[np.int64]:
    return np.asarray(values).astype("datetime64[s]").astype(np.int64)


def load_sequences(path: Path, examples: Examples) -> tuple[Sequences, Lengths]:
    """The recent-match sequence of every example, in the order of `examples`."""
    query = """
        SELECT platform || ':' || puuid AS player, cutoff, rn, hours_before_cutoff, gap_hours,
               duration_min, win::INT AS win, kills, deaths, assists, remake::INT AS remake,
               surrendered::INT AS surrendered, queue_id, coalesce(team_position, '') AS role,
               coalesce(same_champion::INT, 0) AS same_champion
        FROM read_parquet(?)
    """
    with duckdb.connect() as con:
        c = con.execute(query, [str(path)]).fetchnumpy()
    row_of = {
        key: i
        for i, key in enumerate(
            zip(examples.player.tolist(), _seconds(examples.cutoff).tolist(), strict=True)
        )
    }
    keys = zip(np.asarray(c["player"]).tolist(), _seconds(c["cutoff"]).tolist(), strict=True)
    rows = np.array([row_of.get(k, -1) for k in keys], dtype=np.int64)
    keep = rows >= 0  # sequences of ineligible or unlabelled pairs aren't needed
    rows, rn = rows[keep], np.asarray(c["rn"], dtype=np.int64)[keep]

    def col(name: str) -> NDArray[np.float64]:
        return np.ma.filled(np.ma.asarray(c[name], dtype=np.float64), np.nan)[keep]

    gap = col("gap_hours")
    queue = np.asarray(c["queue_id"])[keep]
    role = np.asarray(c["role"])[keep]
    steps = np.column_stack(
        [
            np.log1p(col("hours_before_cutoff")),
            np.log1p(np.nan_to_num(gap, nan=0.0).clip(min=0)),
            np.isnan(gap),
            col("duration_min") / 30,
            col("win"),
            np.log1p(col("kills")),
            np.log1p(col("deaths")),
            np.log1p(col("assists")),
            col("remake"),
            col("surrendered"),
            *(queue == q for q in QUEUES),
            ~np.isin(queue, QUEUES),
            *(role == r for r in ROLES),
            ~np.isin(role, ROLES),
            col("same_champion"),
        ]
    ).astype(np.float32)

    lengths = np.bincount(rows, minlength=len(examples)).astype(np.int64)
    seq = np.zeros((len(examples), SEQ_LEN, len(STEP_FEATURES)), dtype=np.float32)
    seq[rows, lengths[rows] - rn] = steps  # rn = 1 (newest) goes last
    return seq, lengths


@dataclass(frozen=True)
class Scaler:
    """Fitted on training rows: the tabular design (signed log, median fill, missing-value
    indicators, standardised) and the mean and scale of each sequence step feature."""

    medians: list[float]
    indicators: list[int]
    mean: list[float]
    scale: list[float]
    step_mean: list[float]
    step_scale: list[float]

    @staticmethod
    def _design(x: Matrix, medians: NDArray[np.float64], indicators: list[int]) -> Matrix:
        z = signed_log1p(x)
        missing = np.isnan(z)
        return np.hstack([np.where(missing, medians, z), missing[:, indicators]])

    @classmethod
    def fit(cls, x: Matrix, seq: Sequences, lengths: Lengths) -> Self:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN column; median set to 0
            medians = np.nan_to_num(np.nanmedian(signed_log1p(x), axis=0), nan=0.0)
        indicators = np.flatnonzero(np.isnan(x).any(axis=0)).tolist()
        design = cls._design(x, medians, indicators)
        valid = np.arange(SEQ_LEN)[None, :] < lengths[:, None]
        steps = seq[valid] if valid.any() else np.zeros((1, seq.shape[2]), dtype=np.float32)

        def safe(std: NDArray[np.float64]) -> list[float]:
            return [float(v) for v in np.where(std > 0, std, 1.0)]

        return cls(
            medians=medians.tolist(),
            indicators=indicators,
            mean=design.mean(axis=0).tolist(),
            scale=safe(design.std(axis=0)),
            step_mean=steps.mean(axis=0).astype(np.float64).tolist(),
            step_scale=safe(steps.std(axis=0).astype(np.float64)),
        )

    def static(self, x: Matrix) -> NDArray[np.float32]:
        design = self._design(x, np.asarray(self.medians), self.indicators)
        return ((design - np.asarray(self.mean)) / np.asarray(self.scale)).astype(np.float32)

    def steps(self, seq: Sequences, lengths: Lengths) -> Sequences:
        """Standardised steps; padding beyond each length stays zero."""
        z = (seq - np.asarray(self.step_mean, dtype=np.float32)) / np.asarray(
            self.step_scale, dtype=np.float32
        )
        valid = np.arange(SEQ_LEN)[None, :, None] < lengths[:, None, None]
        return np.where(valid, z, 0.0).astype(np.float32)
