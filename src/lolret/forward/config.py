"""Forward-test configuration, loaded from YAML (see `configs/forward.yaml`, ADR 0011).

A forward test reuses a finished collection run: its players, its cached responses and its
examples, which become the training data. It adds one cutoff after the run's last label
window, predicts for every player eligible there, freezes the predictions by hash, and scores
them once the label window has happened.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field

from lolret.collect.config import Bucket, CollectConfig, load_config
from lolret.model.config import TrainConfig, load_train_config

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ForwardError(RuntimeError):
    """A step was run out of order, or its inputs don't match what was frozen."""


class ForwardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str  # data/raw/<name>.sqlite, data/raw/<name>-labels.sqlite, data/forward/<name>/
    base_run: Path  # collection config of the run whose players and responses are reused
    train: Path  # training config: its dataset is the base run's examples
    cutoff: date  # UTC midnight
    # Frozen predictions: entry name -> SHA-256 of its file, committed before any label exists.
    entries: dict[str, Sha256] = Field(default_factory=dict)


@dataclass(frozen=True)
class Forward:
    cfg: ForwardConfig
    base: CollectConfig
    train: TrainConfig
    collect: CollectConfig  # the base run's settings with the forward cutoff as its only cutoff

    @property
    def name(self) -> str:
        return self.cfg.name

    @property
    def cutoff(self) -> datetime:
        return self.collect.cutoffs[0]

    @property
    def feature_buckets(self) -> list[Bucket]:
        return [b for b in self.collect.buckets if b[1] <= self.cutoff]

    @property
    def label_buckets(self) -> list[Bucket]:
        return [b for b in self.collect.buckets if b[0] >= self.cutoff]

    @property
    def label_window_end(self) -> datetime:
        return self.collect.range_end


def load_forward(path: Path) -> Forward:
    with path.open(encoding="utf-8") as f:
        cfg = ForwardConfig.model_validate(yaml.safe_load(f))
    base = load_config(cfg.base_run)
    train = load_train_config(cfg.train)
    if train.dataset != base.run_name:
        raise ValueError(
            f"{cfg.train} trains on '{train.dataset}', but the base run is '{base.run_name}'"
        )
    collect = CollectConfig.model_validate(
        base.model_dump() | {"run_name": cfg.name, "latest_cutoff": cfg.cutoff, "n_cutoffs": 1}
    )
    if (collect.range_start - base.range_start) % timedelta(days=base.bucket_days):
        raise ValueError(
            f"the cutoff must fall on the base run's {base.bucket_days}-day bucket grid (it starts "
            f"{base.range_start:%Y-%m-%d}), so the cached weekly match lists can be reused"
        )
    if collect.cutoffs[0] < base.range_end:
        raise ValueError(
            f"the cutoff must not come before the base run's last label window ends "
            f"({base.range_end:%Y-%m-%d}), so every training label is known at the cutoff"
        )
    return Forward(cfg, base, train, collect)
