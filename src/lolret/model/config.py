"""Training configuration, loaded from YAML (see `configs/train.yaml`).

Design: docs/decisions/0008-classical-model-evaluation.md.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt


class LightGBMParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    learning_rate: PositiveFloat
    num_leaves: int = Field(ge=2)
    min_child_samples: PositiveInt
    feature_fraction: float = Field(gt=0, le=1)
    bagging_fraction: float = Field(gt=0, le=1)
    lambda_l2: float = Field(ge=0)
    max_rounds: PositiveInt
    early_stopping_rounds: PositiveInt


class TrainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset: str  # run name: reads data/processed/<dataset>/, writes data/models/<dataset>/
    test_fraction: float = Field(gt=0, lt=1)  # share of players held out for the test set
    cv_folds: int = Field(ge=2)  # player-grouped folds inside the training set
    logreg_c: list[PositiveFloat] = Field(min_length=1)  # inverse L2 strengths to try
    lightgbm: LightGBMParams
    bootstrap: PositiveInt  # resamples for confidence intervals on the test set
    seed: int


def load_train_config(path: Path) -> TrainConfig:
    with path.open(encoding="utf-8") as f:
        return TrainConfig.model_validate(yaml.safe_load(f))
