"""Neural-net training configuration, loaded from YAML (see `configs/train_nn.yaml`).

Design: docs/decisions/0004-neural-nets-on-colab.md and 0012-neural-nets.md.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt

from lolret.model.config import TrainConfig, load_train_config


class NNConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    train: Path  # the Phase 4a config: dataset, test split, folds, bootstrap and seed
    max_epochs: PositiveInt
    patience: PositiveInt  # epochs without a better validation loss before stopping
    batch_size: PositiveInt
    learning_rate: PositiveFloat
    weight_decay: float = Field(ge=0)
    dropout: float = Field(ge=0, lt=1)
    seeds: PositiveInt  # independently initialised nets per model, averaged
    mlp_hidden: list[PositiveInt] = Field(min_length=1)
    gru_hidden: PositiveInt
    static_hidden: PositiveInt


def load_nn_config(path: Path) -> tuple[NNConfig, TrainConfig]:
    with path.open(encoding="utf-8") as f:
        cfg = NNConfig.model_validate(yaml.safe_load(f))
    return cfg, load_train_config(cfg.train)
