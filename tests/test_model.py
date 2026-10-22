"""Model tests: loading and splitting, each model, calibration, evaluation, and `lolret train`."""

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from conftest import REPO_ROOT
from typer.testing import CliRunner

from lolret.cli import app
from lolret.dataset.build import build_examples
from lolret.dataset.extract import BUCKETS_SCHEMA, MATCHES_SCHEMA, PLAYERS_SCHEMA, Tables
from lolret.model.config import LightGBMParams, TrainConfig, load_train_config
from lolret.model.data import FEATURES, load_examples, split_by_player_and_time
from lolret.model.evaluate import brier, evaluate, reliability, scores
from lolret.model.models import Ladder, LogReg, Platt, Recency, logit, sigmoid
from lolret.model.train import (
    CARD_FILE,
    METRICS_FILE,
    InsufficientDataError,
    examples_path,
    train_and_evaluate,
)

CUTOFFS = [datetime(2026, 7, 30), datetime(2026, 8, 27), datetime(2026, 9, 24)]
DAYS = FEATURES.index("days_since_last_game")
WIN_RATE = FEATURES.index("win_rate")


def config(**overrides: Any) -> TrainConfig:
    params = {
        "dataset": "synthetic",
        "test_fraction": 0.3,
        "cv_folds": 3,
        "logreg_c": [0.1, 1.0],
        "lightgbm": LightGBMParams(
            learning_rate=0.1,
            num_leaves=7,
            min_child_samples=20,
            feature_fraction=1.0,
            bagging_fraction=1.0,
            lambda_l2=1.0,
            max_rounds=200,
            early_stopping_rounds=20,
        ),
        "bootstrap": 50,
        "seed": 7,
    }
    return TrainConfig(**(params | overrides))


def write_examples(path: Path, n_players: int = 600, seed: int = 0) -> list[str]:
    """A synthetic `examples.parquet` where churn depends on recency and recent activity.

    Some rows are ineligible or unlabelled (they must be dropped) and about 5% of match
    features are NULL. Returns the puuids, to check that none leak into the outputs.
    """
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    puuids = [f"puuid-{i:04d}-secret" for i in range(n_players)]
    for i, puuid in enumerate(puuids):
        for cutoff in CUTOFFS:
            days = float(rng.exponential(6.0))
            games = float(rng.poisson(8 * np.exp(-days / 6)))
            churned = rng.random() < sigmoid(np.array(-2.5 + 0.3 * days - 0.15 * games))
            row: dict[str, Any] = {name: float(rng.random()) for name in FEATURES}
            row |= {
                "platform": ("na1", "euw1", "kr")[i % 3],
                "puuid": puuid,
                "tier": "GOLD",
                "division": "II",
                "cutoff": cutoff,
                "eligible": rng.random() < 0.9,
                "churned": None if rng.random() < 0.03 else bool(churned),
                "games_0_7d": games,
                "days_since_last_game": days,
            }
            for name in FEATURES[5:]:  # match features: sometimes NULL
                if rng.random() < 0.05:
                    row[name] = None
            rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)
    return puuids


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    write_examples(examples_path(tmp_path, "synthetic"))
    return tmp_path


def test_features_are_exactly_the_dataset_feature_columns() -> None:
    empty = Tables(
        PLAYERS_SCHEMA.empty_table(), BUCKETS_SCHEMA.empty_table(), MATCHES_SCHEMA.empty_table()
    )
    with duckdb.connect() as con:
        build_examples(con, empty, CUTOFFS)
        columns = [c[0] for c in con.execute("DESCRIBE examples").fetchall()]
    keys = ["platform", "puuid", "tier", "division", "cutoff", "eligible", "churned"]

    assert columns == keys + list(FEATURES)


def test_load_keeps_eligible_labelled_rows_with_nan_for_nulls(data_dir: Path) -> None:
    path = examples_path(data_dir, "synthetic")
    raw = duckdb.execute("SELECT * FROM read_parquet(?)", [str(path)]).fetchnumpy()
    keep = raw["eligible"] & ~np.ma.getmaskarray(raw["churned"])

    examples = load_examples(path)

    assert len(examples) == int(keep.sum())
    assert examples.x.shape == (len(examples), len(FEATURES))
    assert np.isnan(examples.x[:, WIN_RATE]).any()
    assert not np.isnan(examples.x[:, :5]).any()  # activity counts are never NULL
    assert set(np.unique(examples.y)) == {0, 1}


def test_split_holds_out_players_and_tests_on_the_latest_cutoff(data_dir: Path) -> None:
    examples = load_examples(examples_path(data_dir, "synthetic"))

    train, test = split_by_player_and_time(examples, test_fraction=0.3, seed=1)

    assert not set(train.player) & set(test.player)
    assert set(test.cutoff) == {np.datetime64(CUTOFFS[-1])}
    assert np.datetime64(CUTOFFS[-1]) not in set(train.cutoff)
    assert 0.2 < len(np.unique(test.player)) / len(np.unique(examples.player)) < 0.4
    # A player's side depends on the player alone, so it survives the dataset changing.
    _, test_of_half = split_by_player_and_time(examples.subset(examples.x[:, DAYS] < 5), 0.3, 1)
    assert set(test_of_half.player) <= set(test.player)


def test_recency_ranks_by_days_since_the_last_game() -> None:
    rng = np.random.default_rng(0)
    x = np.zeros((500, len(FEATURES)))
    x[:, DAYS] = rng.exponential(6.0, 500)
    y = (rng.random(500) < sigmoid(-2 + 0.3 * x[:, DAYS])).astype(np.int64)
    model = Recency.fit(x, y)

    probe = np.zeros((3, len(FEATURES)))
    probe[:, DAYS] = [np.nan, 1.0, 20.0]
    p = model.predict(probe)

    assert model.coef > 0
    assert p[0] < p[1] < p[2]
    assert p[0] == pytest.approx(model.predict(np.zeros((1, len(FEATURES))))[0])


def test_logistic_regression_handles_missing_values() -> None:
    rng = np.random.default_rng(0)
    x = rng.random((400, len(FEATURES)))
    y = (x[:, DAYS] + 0.2 * rng.random(400) > 0.6).astype(np.int64)
    x[rng.random(400) < 0.1, WIN_RATE] = np.nan

    model = LogReg.fit(x, y, c=1.0)
    p = model.predict(x)

    assert model.indicators == [WIN_RATE]
    assert model.design_names()[-1] == "win_rate_missing"
    assert np.isfinite(p).all()
    assert scores(y, p)["roc_auc"] > 0.9  # type: ignore[operator]


def test_platt_scaling_repairs_an_overconfident_probability() -> None:
    rng = np.random.default_rng(0)
    true_p = sigmoid(rng.normal(-1.0, 1.0, 5000))
    y = (rng.random(5000) < true_p).astype(np.int64)
    overconfident = sigmoid(3 * logit(true_p))

    platt = Platt.fit(overconfident, y)

    assert platt.a == pytest.approx(1 / 3, abs=0.05)
    assert brier(y, platt.apply(overconfident)) < brier(y, overconfident)


def test_scores_need_both_classes_for_ranking_metrics() -> None:
    result = scores(np.zeros(4, dtype=np.int64), np.full(4, 0.2))

    assert result["pr_auc"] is None
    assert result["roc_auc"] is None
    assert result["brier"] == pytest.approx(0.04)


def test_bootstrap_intervals_are_reproducible_and_paired() -> None:
    rng = np.random.default_rng(0)
    y = (rng.random(300) < 0.3).astype(np.int64)
    preds = {"base": np.full(300, 0.3), "good": np.clip(y * 0.5 + rng.random(300) * 0.5, 0, 1)}

    first = evaluate(y, preds, baseline="base", n_boot=200, seed=3)
    second = evaluate(y, preds, baseline="base", n_boot=200, seed=3)
    results, comparison = first

    assert first == second
    lo, hi = results["good"]["pr_auc_ci"]
    assert lo <= results["good"]["pr_auc"] <= hi
    assert results["base"]["roc_auc"] == 0.5
    assert comparison["good"]["pr_auc_diff_ci"][0] > 0
    assert "base" not in comparison


def test_reliability_bins_cover_every_example() -> None:
    rng = np.random.default_rng(0)
    p = rng.random(95)
    y = (rng.random(95) < p).astype(np.int64)

    bins = reliability(y, p)

    assert len(bins) == 10
    assert sum(b["n"] for b in bins) == 95
    assert [b["predicted"] for b in bins] == sorted(b["predicted"] for b in bins)


def test_train_writes_models_that_reload_to_the_same_predictions(data_dir: Path) -> None:
    puuids = write_examples(examples_path(data_dir, "synthetic"))

    summary = train_and_evaluate(config(), data_dir)

    out = summary.out_dir
    assert {p.name for p in out.iterdir()} == {
        "models.json",
        "lightgbm.txt",
        METRICS_FILE,
        CARD_FILE,
    }
    _, test = split_by_player_and_time(
        load_examples(examples_path(data_dir, "synthetic")), 0.3, seed=7
    )
    reloaded = Ladder.load(out).predict(test.x)
    for name, result in summary.test.items():
        assert scores(test.y, reloaded[name])["pr_auc"] == pytest.approx(result["pr_auc"])
    # The signal is strong, so the real models must clear the majority-class floor.
    floor = summary.test["majority"]["pr_auc"]
    assert summary.test["logreg"]["pr_auc"] > floor + 0.1
    assert summary.test["lightgbm"]["pr_auc"] > floor + 0.1
    card = (out / CARD_FILE).read_text(encoding="utf-8")
    assert "Recency rule" in card
    assert "Preliminary" in card  # fewer than 200 churners in this small test set
    # Nothing written identifies a player.
    for file in out.iterdir():
        text = file.read_text(encoding="utf-8")
        assert not any(puuid in text for puuid in puuids), file.name


def test_reloading_rejects_a_different_feature_list(data_dir: Path) -> None:
    out = train_and_evaluate(config(), data_dir).out_dir
    models = out / "models.json"
    models.write_text(models.read_text(encoding="utf-8").replace('"kda"', '"kda_v2"'), "utf-8")

    with pytest.raises(ValueError, match="different feature list"):
        Ladder.load(out)


def test_train_refuses_too_little_data(tmp_path: Path) -> None:
    write_examples(examples_path(tmp_path, "synthetic"), n_players=6)

    with pytest.raises(InsufficientDataError):
        train_and_evaluate(config(), tmp_path)


def test_train_config_in_the_repo_is_valid() -> None:
    cfg = load_train_config(REPO_ROOT / "configs" / "train.yaml")

    assert cfg.dataset == "v1"


def test_cli_train_without_a_dataset_exits_with_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))

    result = CliRunner().invoke(app, ["train", "-c", str(REPO_ROOT / "configs" / "train.yaml")])

    assert result.exit_code == 1


def test_cli_train_writes_the_model_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_dir: Path
) -> None:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    cfg_path = tmp_path / "train.yaml"
    cfg_path.write_text(config().model_dump_json(), encoding="utf-8")  # JSON is valid YAML

    result = CliRunner().invoke(app, ["train", "-c", str(cfg_path)])

    assert result.exit_code == 0, result.output
    assert (data_dir / "models" / "synthetic" / CARD_FILE).exists()
