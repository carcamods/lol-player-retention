"""Neural-net tests: sequence layout, a CPU smoke test of both nets, and `lolret train-nn`."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import torch
import yaml
from conftest import REPO_ROOT
from test_model import config as train_config
from test_model import write_examples
from typer.testing import CliRunner

from lolret.cli import app
from lolret.model.data import FEATURES, load_examples
from lolret.model.train import CARD_FILE, METRICS_FILE, examples_path, train_and_evaluate
from lolret.nn.config import NNConfig, load_nn_config
from lolret.nn.data import SEQ_LEN, STEP_FEATURES, Scaler, load_sequences, sequences_path
from lolret.nn.models import MLP, GRUNet
from lolret.nn.train import (
    AVERAGE,
    MissingLadderError,
    fit_net,
    load_nets,
    predict,
    to_batch,
    train_nn_and_evaluate,
)

T = datetime(2026, 9, 24)


def nn_config(**overrides: Any) -> NNConfig:
    params: dict[str, Any] = {
        "train": Path("train.yaml"),
        "max_epochs": 6,
        "patience": 2,
        "batch_size": 64,
        "learning_rate": 0.01,
        "weight_decay": 0.0,
        "dropout": 0.1,
        "seeds": 1,
        "mlp_hidden": [8],
        "gru_hidden": 8,
        "static_hidden": 8,
    }
    return NNConfig(**(params | overrides))


def step(rn: int, hours: float, **overrides: Any) -> dict[str, Any]:
    row = {
        "rn": rn,
        "hours_before_cutoff": hours,
        "gap_hours": 2.0,
        "duration_min": 30.0,
        "win": True,
        "kills": 3,
        "deaths": 2,
        "assists": 4,
        "remake": False,
        "surrendered": False,
        "queue_id": 420,
        "team_position": "TOP",
        "same_champion": False,
    }
    return row | overrides


def write_sequences(path: Path, examples_file: Path, seed: int = 0) -> None:
    """Random recent games for every example in a synthetic `examples.parquet`; players who
    churned played their last game longer before the cutoff."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    keys = duckdb.execute(
        "SELECT platform, puuid, cutoff, coalesce(churned, false) FROM read_parquet(?)",
        [str(examples_file)],
    ).fetchall()
    for platform, puuid, cutoff, churned in keys:
        hours = rng.exponential(200 if churned else 60)
        for rn in range(1, int(rng.integers(0, SEQ_LEN + 1)) + 1):
            hours += rng.exponential(10)
            key = {"platform": platform, "puuid": puuid, "cutoff": cutoff}
            rows.append(key | step(rn, hours, win=bool(rng.random() < 0.5)))
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


def test_sequences_are_laid_out_oldest_first(tmp_path: Path) -> None:
    examples_file = tmp_path / "examples.parquet"
    row = {name: 1.0 for name in FEATURES}
    common = {"platform": "na1", "tier": "GOLD", "division": "II", "cutoff": T}
    pq.write_table(
        pa.Table.from_pylist(
            [
                common | row | {"puuid": "a", "eligible": True, "churned": False},
                common | row | {"puuid": "b", "eligible": True, "churned": True},
            ]
        ),
        examples_file,
    )
    key = {"platform": "na1", "puuid": "a", "cutoff": T}
    seq_file = tmp_path / "sequences.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                key | step(1, 2.0, queue_id=450, team_position=None),
                key | step(2, 5.0),
                key | step(3, 30.0, gap_hours=None),
            ]
        ),
        seq_file,
    )

    seq, lengths = load_sequences(seq_file, load_examples(examples_file))

    assert seq.shape == (2, SEQ_LEN, len(STEP_FEATURES))
    assert lengths.tolist() == [3, 0]  # player b had no finished game before the cutoff
    hours = STEP_FEATURES.index("log_hours_before_cutoff")
    assert np.expm1(seq[0, :3, hours]) == pytest.approx([30.0, 5.0, 2.0])  # oldest first
    assert seq[0, 0, STEP_FEATURES.index("gap_missing")] == 1
    assert seq[0, 2, STEP_FEATURES.index("queue_450")] == 1
    assert seq[0, 2, STEP_FEATURES.index("role_none")] == 1
    assert not seq[0, 3:].any()
    assert not seq[1].any()


@pytest.mark.parametrize("kind", ["mlp", "gru"])
def test_nets_give_one_logit_per_example_and_learn_on_cpu(kind: str) -> None:
    """CPU smoke test: right output shape (empty histories included), and the loss falls."""
    rng = np.random.default_rng(0)
    n = 400
    x = rng.normal(size=(n, len(FEATURES)))
    seq = rng.normal(size=(n, SEQ_LEN, len(STEP_FEATURES))).astype(np.float32)
    lengths = rng.integers(0, SEQ_LEN + 1, size=n)
    y = (x[:, 0] + seq[:, 0, 0] > 0).astype(np.int64)
    scaler = Scaler.fit(x, seq, lengths)
    data = to_batch(scaler, x, seq, lengths, y)
    cfg = nn_config(learning_rate=0.02)
    torch.manual_seed(0)
    net = (
        MLP(len(scaler.mean), cfg.mlp_hidden, 0.0)
        if kind == "mlp"
        else GRUNet(len(scaler.mean), len(STEP_FEATURES), 8, 8, 0.0)
    )

    def loss() -> float:
        p = np.clip(predict(net, data), 1e-6, 1 - 1e-6)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

    before = loss()
    fit_net(net, data, cfg, seed=0, epochs=10)

    assert net(data.static, data.seq, data.lengths).shape == (n,)
    assert loss() < before - 0.05


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    source = examples_path(tmp_path, "synthetic")
    write_examples(source, n_players=300)
    write_sequences(sequences_path(tmp_path, "synthetic"), source)
    return tmp_path


def test_train_nn_adds_the_nets_to_the_model_card(data_dir: Path) -> None:
    cfg, tcfg = nn_config(), train_config()
    train_and_evaluate(tcfg, data_dir)

    summary = train_nn_and_evaluate(cfg, tcfg, data_dir)

    model_dir = data_dir / "models" / "synthetic"
    metrics = json.loads((model_dir / METRICS_FILE).read_text(encoding="utf-8"))
    assert {"mlp", "gru", AVERAGE} <= set(metrics["test"])
    assert set(metrics["nn"]["vs_lightgbm"]) == {"mlp", "gru", AVERAGE}
    assert {"lightgbm", "mlp", "gru", AVERAGE} <= set(metrics["vs_baseline"])
    card = (model_dir / CARD_FILE).read_text(encoding="utf-8")
    assert "## Neural nets" in card
    assert "LightGBM + GRU average" in card
    assert set(summary.test) == {"mlp", "gru", AVERAGE}
    written = " ".join(p.read_text(encoding="utf-8") for p in model_dir.rglob("*.json"))
    assert "secret" not in written + card  # the synthetic puuids end in "-secret"


def test_saved_nets_reload_to_the_same_predictions(data_dir: Path) -> None:
    cfg, tcfg = nn_config(), train_config()
    train_and_evaluate(tcfg, data_dir)
    train_nn_and_evaluate(cfg, tcfg, data_dir)
    examples = load_examples(examples_path(data_dir, "synthetic"))
    seq, lengths = load_sequences(sequences_path(data_dir, "synthetic"), examples)

    _, nets = load_nets(data_dir, "synthetic")
    _, again = load_nets(data_dir, "synthetic")

    for kind in ("mlp", "gru"):
        first = nets[kind].predict(examples.x, seq, lengths)
        assert first == pytest.approx(again[kind].predict(examples.x, seq, lengths))
        assert ((first > 0) & (first < 1)).all()


def test_train_nn_needs_the_classical_models_first(data_dir: Path) -> None:
    with pytest.raises(MissingLadderError, match="lolret train"):
        train_nn_and_evaluate(nn_config(), train_config(), data_dir)


def test_cli_train_nn_without_models_exits_with_an_error(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    (tmp_path / "train.yaml").write_text(train_config().model_dump_json(), encoding="utf-8")
    nn_yaml = nn_config(train=tmp_path / "train.yaml").model_dump(mode="json")
    (tmp_path / "nn.yaml").write_text(yaml.safe_dump(nn_yaml), encoding="utf-8")

    result = CliRunner().invoke(app, ["train-nn", "-c", str(tmp_path / "nn.yaml")])

    assert result.exit_code == 1


def test_nn_config_in_the_repo_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)

    cfg, tcfg = load_nn_config(REPO_ROOT / "configs" / "train_nn.yaml")

    assert tcfg.dataset == "v1"
    assert cfg.seeds >= 1
