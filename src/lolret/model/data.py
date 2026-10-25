"""Load the modelling examples and split them by player and by time.

Only eligible pairs with a known label are modelled (ADR 0006). The test set is a held-out
share of players at the latest cutoff; training uses the other players at the earlier
cutoffs. So the test players were never seen in training, and every training label was known
before the test cutoff (ADR 0008).
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
from numpy.typing import NDArray

# Model inputs, in matrix column order (the order of features.sql). Definitions: docs/features.md.
FEATURES: tuple[str, ...] = (
    "games_0_7d",
    "games_8_14d",
    "games_15_28d",
    "games_29_56d",
    "active_weeks_8w",
    "recent_games",
    "days_since_last_game",
    "win_rate",
    "win_rate_last5",
    "loss_streak",
    "kda",
    "deaths_avg",
    "duration_min_avg",
    "remake_share",
    "surrendered_loss_share",
    "ranked_share",
    "aram_share",
    "champion_diversity",
    "gap_hours_median",
    "last_session_games",
    "main_role_share",
)

Matrix = NDArray[np.float64]
Vector = NDArray[np.float64]
Labels = NDArray[np.int64]


@dataclass(frozen=True)
class Examples:
    """Eligible, labelled examples. Row i of every array is the same (player, cutoff)."""

    x: Matrix  # (rows, len(FEATURES)), NaN where the feature is NULL
    y: Labels  # 1 = churned
    player: NDArray[np.str_]  # "platform:puuid", for grouping only; never written out
    cutoff: NDArray[np.datetime64]

    def __len__(self) -> int:
        return len(self.y)

    def subset(self, mask: NDArray[np.bool_]) -> "Examples":
        return Examples(self.x[mask], self.y[mask], self.player[mask], self.cutoff[mask])


UNKNOWN = -1  # label of an example whose label window hasn't happened yet


def load_examples(path: Path, *, labelled: bool = True) -> Examples:
    """Read `examples.parquet` (from `lolret build`), keeping eligible pairs with a label.

    With `labelled=False`, eligible pairs without a label are kept too, with `y = UNKNOWN`:
    the forward test predicts for them before their outcome exists.
    """
    columns = ", ".join(f"coalesce({name}::DOUBLE, 'NaN'::DOUBLE) AS {name}" for name in FEATURES)
    where = "eligible AND churned IS NOT NULL" if labelled else "eligible"
    # Column names come from FEATURES, a constant in this module, not from user input.
    query = (
        f"SELECT platform || ':' || puuid AS player, cutoff, "  # noqa: S608
        f"coalesce(churned::INT, {UNKNOWN}) AS y, {columns} "
        f"FROM read_parquet(?) WHERE {where} ORDER BY player, cutoff"
    )
    with duckdb.connect() as con:
        cols = con.execute(query, [str(path)]).fetchnumpy()
    return Examples(
        x=np.column_stack([np.asarray(cols[name], dtype=np.float64) for name in FEATURES])
        if len(cols["y"])
        else np.empty((0, len(FEATURES))),
        y=np.asarray(cols["y"], dtype=np.int64),
        player=np.asarray(cols["player"], dtype=np.str_),
        cutoff=np.asarray(cols["cutoff"], dtype="datetime64[s]"),
    )


def in_test_set(player: str, fraction: float, seed: int) -> bool:
    """Whether a player is held out for testing.

    Decided by a hash of the player alone, so a player stays on the same side as the
    dataset grows and the test set only ever gains players.
    """
    digest = hashlib.sha256(f"{seed}:{player}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 < fraction


def split_by_player_and_time(
    examples: Examples, test_fraction: float, seed: int
) -> tuple[Examples, Examples]:
    """Train: other players at earlier cutoffs. Test: held-out players at the latest cutoff."""
    if not len(examples):
        return examples, examples
    latest = examples.cutoff.max()
    held_out = np.array(
        [in_test_set(p, test_fraction, seed) for p in examples.player], dtype=np.bool_
    )
    train = examples.subset(~held_out & (examples.cutoff < latest))
    test = examples.subset(held_out & (examples.cutoff == latest))
    return train, test
