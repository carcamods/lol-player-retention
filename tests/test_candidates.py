"""Candidate features (ADR 0013): loading, the candidate LightGBM, and `lolret train-candidates`."""

import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_model import config as train_config
from test_model import write_examples
from typer.testing import CliRunner

from lolret.cli import app
from lolret.model.candidates import (
    CANDIDATES,
    MODEL,
    RESULTS_FILE,
    candidates_path,
    evaluate_candidates,
    load_candidates,
)
from lolret.model.data import load_examples
from lolret.model.train import examples_path, train_and_evaluate


def write_candidates(path: Path, examples_file: Path, seed: int = 0) -> None:
    """Candidate columns for every row of a synthetic `examples.parquet`; one of them carries
    signal (churners have fewer repeated teammates) and some values are NULL."""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    keys = duckdb.execute(
        "SELECT platform, puuid, cutoff, coalesce(churned, false) FROM read_parquet(?)",
        [str(examples_file)],
    ).fetchall()
    for platform, puuid, cutoff, churned in keys:
        row: dict[str, Any] = {"platform": platform, "puuid": puuid, "cutoff": cutoff}
        row |= {name: float(rng.random()) for name in CANDIDATES}
        row["repeated_teammates"] = int(rng.poisson(1 if churned else 3))
        if rng.random() < 0.05:
            row["summoner_level"] = None
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    source = examples_path(tmp_path, "synthetic")
    write_examples(source)
    write_candidates(candidates_path(tmp_path, "synthetic"), source)
    return tmp_path


def test_candidates_load_in_the_order_of_the_examples(data_dir: Path) -> None:
    examples = load_examples(examples_path(data_dir, "synthetic"))

    x = load_candidates(candidates_path(data_dir, "synthetic"), examples)

    assert x.shape == (len(examples), len(CANDIDATES))
    assert np.isnan(x[:, CANDIDATES.index("summoner_level")]).any()
    churners = x[examples.y == 1, CANDIDATES.index("repeated_teammates")].mean()
    stayers = x[examples.y == 0, CANDIDATES.index("repeated_teammates")].mean()
    assert churners < stayers  # rows line up with their labels


def test_candidates_are_compared_with_the_ladder_on_the_test_set(data_dir: Path) -> None:
    cfg = train_config()
    train_and_evaluate(cfg, data_dir)

    summary = evaluate_candidates(cfg, data_dir)

    assert set(summary["test"]) == {"recency", "lightgbm", MODEL}
    assert summary["vs_lightgbm"]["pr_auc_diff_ci"] is not None
    saved = json.loads((data_dir / "models" / "synthetic" / RESULTS_FILE).read_text("utf-8"))
    assert saved["candidates"] == list(CANDIDATES)
    assert "secret" not in json.dumps(saved)  # no identifiers


def test_cli_train_candidates_needs_the_ladder(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    cfg_path = tmp_path / "train.yaml"
    cfg_path.write_text(train_config().model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(app, ["train-candidates", "-c", str(cfg_path)])

    assert result.exit_code == 1
