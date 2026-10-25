"""Train the neural nets with the Phase 4a protocol and add them to the comparison.

Same test split, folds, bootstrap and seed as `lolret train` (ADR 0008):

- For each of `seeds` initialisations, each net early-stops on every player-grouped fold. The
  out-of-fold predictions, averaged over seeds, fit Platt scaling; the mean stopping epoch sets
  the length of the final runs on the whole training set. The test set chooses nothing.
- The final nets are averaged, calibrated and scored on the test set next to the classical
  ladder (loaded from `lolret train`'s output), plus an average of LightGBM and the GRU.

Output: `data/models/<dataset>/nn/` (one `state_dict` per net and `nn.json`); `metrics.json`
and `model_card.md` next to it gain the nets. Nothing written identifies a player.
"""

import copy
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

import numpy as np
import torch
from torch import Tensor, nn

from lolret.log import get_logger
from lolret.model.card import render_model_card
from lolret.model.config import TrainConfig
from lolret.model.data import (
    Examples,
    Labels,
    Matrix,
    Vector,
    load_examples,
    split_by_player_and_time,
)
from lolret.model.evaluate import evaluate, log_loss, reliability
from lolret.model.models import Fold, Ladder, Platt, player_folds
from lolret.model.train import CARD_FILE, METRICS_FILE, examples_path, models_dir
from lolret.nn.config import NNConfig
from lolret.nn.data import STEP_FEATURES, Lengths, Scaler, Sequences, load_sequences, sequences_path
from lolret.nn.models import MLP, GRUNet

log = get_logger(__name__)

NN_DIR = "nn"
NN_FILE = "nn.json"
KINDS = ("mlp", "gru")
AVERAGE = "lightgbm_gru"  # mean of LightGBM's and the GRU's calibrated probabilities


class MissingLadderError(FileNotFoundError):
    """`lolret train` hasn't been run on this dataset."""


@dataclass(frozen=True)
class Batch:
    """Tensors for a set of examples."""

    static: Tensor
    seq: Tensor
    lengths: Tensor
    y: Tensor

    def __len__(self) -> int:
        return len(self.y)

    def take(self, idx: Tensor) -> "Batch":
        return Batch(self.static[idx], self.seq[idx], self.lengths[idx], self.y[idx])


def to_batch(scaler: Scaler, x: Matrix, seq: Sequences, lengths: Lengths, y: Labels) -> Batch:
    return Batch(
        static=torch.from_numpy(scaler.static(x)),
        seq=torch.from_numpy(scaler.steps(seq, lengths)),
        lengths=torch.from_numpy(lengths),
        y=torch.from_numpy(y.astype(np.float32)),
    )


def make_net(kind: str, cfg: NNConfig, n_static: int) -> nn.Module:
    if kind == "mlp":
        return MLP(n_static, cfg.mlp_hidden, cfg.dropout)
    if kind == "gru":
        return GRUNet(n_static, len(STEP_FEATURES), cfg.gru_hidden, cfg.static_hidden, cfg.dropout)
    raise ValueError(f"unknown network kind: {kind}")


@torch.no_grad()
def predict(net: nn.Module, data: Batch) -> Vector:
    net.eval()
    logits = net(data.static, data.seq, data.lengths)
    return torch.sigmoid(logits).double().numpy()


def fit_net(
    net: nn.Module,
    train: Batch,
    cfg: NNConfig,
    seed: int,
    *,
    val: Batch | None = None,
    epochs: int | None = None,
) -> int:
    """Train in place. With `val`, early-stop on its loss, keep the best weights and return
    that epoch; otherwise train exactly `epochs` epochs."""
    generator = torch.Generator().manual_seed(seed)
    optimiser = torch.optim.AdamW(
        net.parameters(), lr=cfg.learning_rate, weight_decay=cfg.weight_decay
    )
    loss_fn = nn.BCEWithLogitsLoss()
    best_loss, best_epoch, stale = float("inf"), 0, 0
    best_state = copy.deepcopy(net.state_dict())
    for epoch in range(1, (epochs or cfg.max_epochs) + 1):
        net.train()
        for idx in torch.split(torch.randperm(len(train), generator=generator), cfg.batch_size):
            b = train.take(idx)
            optimiser.zero_grad()
            loss_fn(net(b.static, b.seq, b.lengths), b.y).backward()
            optimiser.step()
        if val is None:
            continue
        loss = log_loss(val.y.numpy().astype(np.int64), predict(net, val))
        if loss < best_loss - 1e-6:
            best_loss, best_epoch, stale = loss, epoch, 0
            best_state = copy.deepcopy(net.state_dict())
        else:
            stale += 1
            if stale >= cfg.patience:
                break
    if val is None:
        return epochs or cfg.max_epochs
    net.load_state_dict(best_state)
    return best_epoch


@dataclass
class TrainedNets:
    """One kind of net: its averaged, calibrated ensemble and how it was selected."""

    kind: str
    scaler: Scaler
    epochs: int
    platt: Platt
    oof_log_loss: float
    nets: list[nn.Module]
    oof: Vector | None = None  # out-of-fold predictions, kept only in memory

    def predict(self, x: Matrix, seq: Sequences, lengths: Lengths) -> Vector:
        data = to_batch(self.scaler, x, seq, lengths, np.zeros(len(x), dtype=np.int64))
        mean = np.mean([predict(net, data) for net in self.nets], axis=0)
        return self.platt.apply(mean)

    def save(self, out_dir: Path) -> dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, net in enumerate(self.nets):
            torch.save(net.state_dict(), out_dir / f"{self.kind}_{i}.pt")
        return {
            "scaler": asdict(self.scaler),
            "epochs": self.epochs,
            "platt": [self.platt.a, self.platt.b],
            "oof_log_loss": self.oof_log_loss,
            "nets": len(self.nets),
        }

    @classmethod
    def load(cls, out_dir: Path, kind: str, cfg: NNConfig, saved: dict[str, Any]) -> Self:
        scaler = Scaler(**saved["scaler"])
        nets = []
        for i in range(saved["nets"]):
            net = make_net(kind, cfg, len(scaler.mean))
            net.load_state_dict(torch.load(out_dir / f"{kind}_{i}.pt", weights_only=True))
            nets.append(net)
        return cls(
            kind, scaler, saved["epochs"], Platt(*saved["platt"]), saved["oof_log_loss"], nets
        )


def train_kind(
    kind: str,
    train: Examples,
    seq: Sequences,
    lengths: Lengths,
    folds: list[Fold],
    cfg: NNConfig,
    seed: int,
) -> TrainedNets:
    oof = np.zeros(len(train))
    stops: list[int] = []
    for s in range(cfg.seeds):
        for tr, va in folds:
            scaler = Scaler.fit(train.x[tr], seq[tr], lengths[tr])
            fit_data = to_batch(scaler, train.x[tr], seq[tr], lengths[tr], train.y[tr])
            val_data = to_batch(scaler, train.x[va], seq[va], lengths[va], train.y[va])
            torch.manual_seed(seed + s)
            net = make_net(kind, cfg, len(scaler.mean))
            stops.append(fit_net(net, fit_data, cfg, seed + s, val=val_data))
            oof[va] += predict(net, val_data) / cfg.seeds
    epochs = max(round(float(np.mean(stops))), 1)
    oof_loss = log_loss(train.y, oof)
    log.info("%s: %d epochs (mean early stop), out-of-fold log loss %.4f", kind, epochs, oof_loss)

    scaler = Scaler.fit(train.x, seq, lengths)
    data = to_batch(scaler, train.x, seq, lengths, train.y)
    nets = []
    for s in range(cfg.seeds):
        torch.manual_seed(seed + s)
        net = make_net(kind, cfg, len(scaler.mean))
        fit_net(net, data, cfg, seed + s, epochs=epochs)
        nets.append(net)
    return TrainedNets(kind, scaler, epochs, Platt.fit(oof, train.y), oof_loss, nets, oof)


@dataclass(frozen=True)
class NNSummary:
    out_dir: Path
    test: dict[str, dict[str, Any]]
    vs_lightgbm: dict[str, dict[str, Any]]


def train_nn_and_evaluate(cfg: NNConfig, train_cfg: TrainConfig, data_dir: Path) -> NNSummary:
    model_dir = models_dir(data_dir, train_cfg.dataset)
    metrics_path = model_dir / METRICS_FILE
    if not metrics_path.exists():
        raise MissingLadderError(f"no classical models in {model_dir}: run `lolret train` first")
    metrics: dict[str, Any] = json.loads(metrics_path.read_text(encoding="utf-8"))
    source = examples_path(data_dir, train_cfg.dataset)
    if metrics["examples_sha256"] != _sha256(source):
        raise MissingLadderError(f"{model_dir} was trained on other data: re-run `lolret train`")

    train, test = split_by_player_and_time(
        load_examples(source), train_cfg.test_fraction, train_cfg.seed
    )
    seq_path = sequences_path(data_dir, train_cfg.dataset)
    train_seq, train_len = load_sequences(seq_path, train)
    test_seq, test_len = load_sequences(seq_path, test)
    folds = player_folds(train.player, train_cfg.cv_folds, train_cfg.seed)

    trained = {
        kind: train_kind(kind, train, train_seq, train_len, folds, cfg, train_cfg.seed)
        for kind in KINDS
    }
    preds = Ladder.load(model_dir).predict(test.x)
    for kind, nets in trained.items():
        preds[kind] = nets.predict(test.x, test_seq, test_len)
    preds[AVERAGE] = (preds["lightgbm"] + preds["gru"]) / 2

    common = {"n_boot": train_cfg.bootstrap, "seed": train_cfg.seed}
    results, vs_recency = evaluate(test.y, preds, baseline="recency", **common)
    _, vs_lightgbm = evaluate(test.y, preds, baseline="lightgbm", **common)
    new = [*KINDS, AVERAGE]

    out_dir = model_dir / NN_DIR
    saved = {kind: nets.save(out_dir) for kind, nets in trained.items()}
    (out_dir / NN_FILE).write_text(
        json.dumps({"config": cfg.model_dump(mode="json"), "models": saved}, indent=2) + "\n",
        encoding="utf-8",
    )
    metrics["test"] = results
    metrics["vs_baseline"] = vs_recency
    metrics["reliability"] |= {name: reliability(test.y, preds[name]) for name in new}
    metrics["nn"] = {
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": cfg.model_dump(mode="json"),
        "selection": {
            kind: {"epochs": n.epochs, "oof_log_loss": n.oof_log_loss}
            for kind, n in trained.items()
        },
        "vs_lightgbm": {name: vs_lightgbm[name] for name in new},
    }
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (model_dir / CARD_FILE).write_text(render_model_card(metrics), encoding="utf-8")
    return NNSummary(
        out_dir=out_dir,
        test={name: results[name] for name in new},
        vs_lightgbm=metrics["nn"]["vs_lightgbm"],
    )


def load_nets(data_dir: Path, dataset: str) -> tuple[NNConfig, dict[str, TrainedNets]]:
    """The trained nets of a dataset, as `train_nn_and_evaluate` saved them."""
    out_dir = models_dir(data_dir, dataset) / NN_DIR
    saved = json.loads((out_dir / NN_FILE).read_text(encoding="utf-8"))
    cfg = NNConfig.model_validate(saved["config"])
    return cfg, {
        kind: TrainedNets.load(out_dir, kind, cfg, saved["models"][kind]) for kind in KINDS
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
