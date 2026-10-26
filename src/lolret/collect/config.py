"""Collection run configuration, loaded from YAML (see `configs/collect*.yaml`).

Time is cut into fixed buckets (7 days by default) from the start of the earliest cutoff's
lookback to the end of the latest cutoff's label window. Cutoffs, lookback, spacing and
label window are all whole numbers of buckets, so every feature and label window is a union
of buckets. See docs/decisions/0005-collection-design.md.

`base_run` names an earlier run whose store is read but never written: with the same seed,
dates and ladder pages, its players and responses come from its cache, so raising
`players_per_division` in a new run only requests the new players (ADR 0015).
"""

from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, PositiveInt, model_validator

from lolret.riot.routing import PLATFORM_REGION

Tier = Literal["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"]
Division = Literal["I", "II", "III", "IV"]
Bucket = tuple[datetime, datetime]  # [start, end) in UTC


class CollectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_name: str
    base_run: str | None = None
    platforms: list[str]
    tiers: list[Tier]
    divisions: list[Division]
    players_per_division: PositiveInt
    pages_per_division: PositiveInt
    season_start: date
    latest_cutoff: date
    n_cutoffs: PositiveInt
    cutoff_spacing_days: PositiveInt
    lookback_days: PositiveInt
    label_window_days: PositiveInt
    bucket_days: PositiveInt
    details_per_cutoff: PositiveInt
    seed: int

    @model_validator(mode="after")
    def _check(self) -> Self:
        unknown = sorted(set(self.platforms) - PLATFORM_REGION.keys())
        if unknown:
            raise ValueError(f"unknown platforms: {unknown}")
        if self.base_run == self.run_name:
            raise ValueError("base_run must name another run: a run can't read from itself")
        for name in ("cutoff_spacing_days", "lookback_days", "label_window_days"):
            if getattr(self, name) % self.bucket_days:
                raise ValueError(f"{name} must be a multiple of bucket_days ({self.bucket_days})")
        if self.range_start.date() < self.season_start:
            raise ValueError(
                f"earliest lookback starts {self.range_start.date()}, before the season start "
                f"{self.season_start}; players who quit before the season would be missing"
            )
        return self

    @property
    def cutoffs(self) -> list[datetime]:
        """Cutoff instants (UTC midnight), oldest first."""
        latest = datetime.combine(self.latest_cutoff, time(), tzinfo=UTC)
        step = timedelta(days=self.cutoff_spacing_days)
        return [latest - step * i for i in reversed(range(self.n_cutoffs))]

    @property
    def range_start(self) -> datetime:
        return self.cutoffs[0] - timedelta(days=self.lookback_days)

    @property
    def range_end(self) -> datetime:
        return self.cutoffs[-1] + timedelta(days=self.label_window_days)

    @property
    def buckets(self) -> list[Bucket]:
        step = timedelta(days=self.bucket_days)
        starts: list[datetime] = []
        start = self.range_start
        while start < self.range_end:
            starts.append(start)
            start += step
        return [(s, s + step) for s in starts]

    def require_complete_label_windows(self, now: datetime) -> None:
        """Fail before any request if the latest label window hasn't fully happened yet."""
        if self.range_end > now:
            raise ValueError(
                f"the latest label window ends {self.range_end:%Y-%m-%d %H:%M} UTC, which is in "
                f"the future; move latest_cutoff back to "
                f"{(now - timedelta(days=self.label_window_days)).date()} or earlier"
            )


def load_config(path: Path) -> CollectConfig:
    with path.open(encoding="utf-8") as f:
        return CollectConfig.model_validate(yaml.safe_load(f))
