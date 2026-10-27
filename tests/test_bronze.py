"""The Bronze expansion (ADR 0015): joining the runs, the fresh test players, the rule, and
`lolret train-bronze`."""

import json
from pathlib import Path

import duckdb
import numpy as np
import pytest
from test_model import config as train_config
from test_model import write_examples
from typer.testing import CliRunner

from lolret.cli import app
from lolret.model.bronze import (
    BRONZE_ONLY,
    GENERAL,
    RECENCY,
    RESULTS_FILE,
    RUN,
    above_zero,
    combine,
    evaluate_bronze,
    judge,
    overlap,
)
from lolret.model.data import FEATURES, in_test_set, load_examples
from lolret.model.train import examples_path, models_dir

POOL = 1200  # synthetic players: v1 holds the first 600, half of them Bronze


def write_runs(data_dir: Path) -> list[str]:
    """v1 (players 0-599, even ones Bronze, odd ones Gold) and `bronze` (v1's Bronze players
    with the same rows, plus players 600-1199, all Bronze), cut from one synthetic pool."""
    pool = data_dir / "pool.parquet"
    puuids = write_examples(pool, n_players=POOL)
    index = "CAST(substr(puuid, 7, 4) AS INT)"
    for run, where, tier in (
        ("v1", f"{index} < 600", f"CASE WHEN {index} % 2 = 0 THEN 'BRONZE' ELSE 'GOLD' END"),
        (RUN, f"{index} >= 600 OR {index} % 2 = 0", "'BRONZE'"),
    ):
        path = examples_path(data_dir, run)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Fixed test inputs, not user input.
        duckdb.execute(
            f"COPY (SELECT * REPLACE ({tier} AS tier) FROM '{pool.as_posix()}' "  # noqa: S608
            f"WHERE {where}) TO '{path.as_posix()}' (FORMAT parquet)"
        )
    pool.unlink()
    return puuids


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    write_runs(tmp_path)
    return tmp_path


def test_combine_keeps_base_rows_and_adds_only_new_players(data_dir: Path) -> None:
    base = load_examples(examples_path(data_dir, "v1"))
    run = load_examples(examples_path(data_dir, RUN))
    examples, new = combine(base, run)
    assert len(set(zip(examples.player.tolist(), examples.cutoff.tolist(), strict=True))) == len(
        examples
    )
    assert not new[: len(base)].any()
    assert new[len(base) :].all()
    assert set(examples.player[~new].tolist()) == set(base.player.tolist())
    assert not set(examples.player[new].tolist()) & set(base.player.tolist())
    shared = set(base.player.tolist()) & set(run.player.tolist())
    assert overlap(base, run) == {
        "players": len(shared),
        "rows_aligned": True,
        "labels_identical": True,
        "features_differing": {},
    }


def test_overlap_names_features_that_differ_beyond_rounding(data_dir: Path) -> None:
    base = load_examples(examples_path(data_dir, "v1"))
    run = load_examples(examples_path(data_dir, RUN))
    rows = np.flatnonzero(np.isin(run.player, base.player))
    gap, kda = FEATURES.index("gap_hours_median"), FEATURES.index("kda")
    run.x[rows[:2], gap] += 0.5
    run.x[rows[0], kda] *= 1 + 1e-15  # float rounding, not a difference
    assert overlap(base, run)["features_differing"] == {"gap_hours_median": 2}


def test_rule_needs_the_interval_above_zero() -> None:
    assert above_zero({"pr_auc_diff": 0.02, "pr_auc_diff_ci": [0.001, 0.04]})
    assert not above_zero({"pr_auc_diff": 0.02, "pr_auc_diff_ci": [-0.001, 0.04]})
    assert not above_zero({"pr_auc_diff": 0.0, "pr_auc_diff_ci": None})


def test_judge_keeps_the_general_model_unless_bronze_only_is_clearly_better() -> None:
    rng = np.random.default_rng(0)
    y = (rng.random(400) < 0.25).astype(np.int64)
    signal = y + rng.normal(0, 0.6, len(y))
    noise = rng.normal(0, 1, len(y))
    cfg = train_config()
    same = judge(y, {RECENCY: noise, GENERAL: signal, BRONZE_ONLY: signal}, cfg)
    assert not same["bronze_gets_own_model"]
    assert same["kept"] == GENERAL
    assert same["kept_beats_recency"]
    better = judge(y, {RECENCY: noise, GENERAL: noise, BRONZE_ONLY: signal}, cfg)
    assert better["bronze_gets_own_model"]
    assert better["kept"] == BRONZE_ONLY


def test_evaluate_bronze_tests_only_fresh_bronze_players(data_dir: Path) -> None:
    cfg = train_config(dataset="v1", bootstrap=20)
    summary = evaluate_bronze(cfg, data_dir, curve=(0.5, 1.0))

    run = load_examples(examples_path(data_dir, RUN))
    base = load_examples(examples_path(data_dir, "v1"))
    latest = run.cutoff.max()
    fresh = [
        p
        for p, c in zip(run.player.tolist(), run.cutoff, strict=True)
        if c == latest and p not in set(base.player.tolist()) and in_test_set(p, 0.3, cfg.seed)
    ]
    rule = summary["rule"]
    assert rule["examples"] == len(fresh) == summary["data"]["test"]["players"]
    assert summary["data"]["train_bronze"]["examples"] < summary["data"]["train"]["examples"]
    assert summary["data"]["train"]["cutoffs"] == ["2026-07-30", "2026-08-27"]
    assert summary["overlap"]["features_differing"] == {}
    assert rule["kept"] in (GENERAL, BRONZE_ONLY)
    assert 0 < summary["euw"]["examples"] < rule["examples"]
    assert [p["share"] for p in summary["learning_curve"]] == [0.5, 1.0]
    assert summary["learning_curve"][1]["pr_auc"] == pytest.approx(
        rule["test"][BRONZE_ONLY]["pr_auc"]
    )
    text = (models_dir(data_dir, RUN) / RESULTS_FILE).read_text(encoding="utf-8")
    assert json.loads(text)["runs"] == ["v1", RUN]
    assert "puuid-" not in text
    assert "secret" not in text


def test_cli_train_bronze_writes_the_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_dir: Path
) -> None:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    cfg_path = tmp_path / "train.yaml"
    cfg = train_config(dataset="v1", bootstrap=20)
    cfg_path.write_text(cfg.model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(app, ["train-bronze", "-c", str(cfg_path)])

    assert result.exit_code == 0, result.output
    assert (models_dir(data_dir, RUN) / RESULTS_FILE).exists()


def test_cli_train_bronze_without_the_run_exits_with_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    write_examples(examples_path(tmp_path, "v1"))
    cfg_path = tmp_path / "train.yaml"
    cfg_path.write_text(train_config(dataset="v1").model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(app, ["train-bronze", "-c", str(cfg_path)])

    assert result.exit_code == 1
