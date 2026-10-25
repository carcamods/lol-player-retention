"""Snapshot export (FR4): content, anonymity, and `lolret export`."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest
from conftest import REPO_ROOT
from test_model import CUTOFFS, write_examples
from test_model import config as train_config
from typer.testing import CliRunner

from lolret.cli import app
from lolret.export.snapshot import anonymous_ids, export_snapshot
from lolret.model.data import load_examples, split_by_player_and_time
from lolret.model.train import examples_path, train_and_evaluate

NOW = datetime(2026, 10, 25, tzinfo=UTC)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    source = examples_path(tmp_path, "synthetic")
    write_examples(source, n_players=300)
    train_and_evaluate(train_config(), tmp_path)
    db = tmp_path / "processed" / "synthetic" / "dataset.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute(
            """CREATE TABLE buckets AS
               SELECT DISTINCT e.platform, e.puuid,
                      ?::TIMESTAMP + INTERVAL 7 DAY * w AS bucket_start,
                      ?::TIMESTAMP + INTERVAL 7 DAY * (w + 1) AS bucket_end,
                      (hash(e.puuid, w) % 5)::INTEGER AS games
               FROM read_parquet(?) AS e, range(-12, 4) AS r(w)""",
            [CUTOFFS[-1], CUTOFFS[-1], str(source)],
        )
    return tmp_path


def exported(data_dir: Path, salt: bytes) -> dict:  # type: ignore[type-arg]
    summary = export_snapshot(train_config(), data_dir, now=NOW, salt=salt)
    return json.loads(summary.path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_snapshot_has_every_held_out_player_and_no_identifier(data_dir: Path) -> None:
    snap = exported(data_dir, b"salt")
    text = json.dumps(snap)

    players = snap["players"]
    assert snap["meta"]["players"] == len(players) > 0
    assert snap["meta"]["cutoff"] == f"{CUTOFFS[-1]:%Y-%m-%d}"
    assert [p["id"] for p in players] == [f"Player {i:04d}" for i in range(1, len(players) + 1)]
    assert "secret" not in text  # every synthetic puuid ends in "-secret"
    assert "puuid" not in text
    for p in players:
        assert 0 < p["churn"] < 1
        assert len(p["drivers"]) == 3
        assert len(p["weeks"]) == 12
        assert p["region"] in {"NA", "EUW", "KR"}
    assert {"recency", "lightgbm"} <= set(snap["metrics"])
    assert len(snap["metrics"]["lightgbm"]["pr_auc_ci"]) == 2
    assert "lightgbm" in snap["vs_recency"]
    assert snap["train"]["examples"] > 0


def test_numbers_depend_on_the_salt_only(data_dir: Path) -> None:
    first, same = exported(data_dir, b"one"), exported(data_dir, b"one")
    other = exported(data_dir, b"two")

    def by_id(snap: dict) -> list[float]:  # type: ignore[type-arg]
        return [p["churn"] for p in snap["players"]]

    assert by_id(first) == by_id(same)
    assert by_id(first) != by_id(other)  # another salt numbers players differently
    assert sorted(by_id(first)) == sorted(by_id(other))  # but they are the same players


def test_anonymous_ids_are_a_permutation() -> None:
    players = [f"na1:p{i}" for i in range(50)]

    ids = anonymous_ids(players, b"s")

    assert sorted(ids.values()) == [f"Player {i:04d}" for i in range(1, 51)]
    assert [ids[p] for p in players] != sorted(ids.values())  # not the input order


def test_the_timeline_covers_8_weeks_before_and_4_after(data_dir: Path) -> None:
    snap = exported(data_dir, b"salt")
    cfg = train_config()
    _, test = split_by_player_and_time(
        load_examples(examples_path(data_dir, "synthetic")), cfg.test_fraction, cfg.seed
    )
    player = test.player[0]
    shown = next(
        p
        for p in snap["players"]
        if p["id"] == anonymous_ids(test.player.tolist(), b"salt")[player]
    )
    platform, puuid = player.split(":", 1)
    db = data_dir / "processed" / "synthetic" / "dataset.duckdb"
    with duckdb.connect(str(db), read_only=True) as con:
        expected = [
            g
            for (g,) in con.execute(
                "SELECT games FROM buckets WHERE platform = ? AND puuid = ? "
                "AND bucket_start >= ? AND bucket_start < ? ORDER BY bucket_start",
                [
                    platform,
                    puuid,
                    CUTOFFS[-1] - timedelta(weeks=8),
                    CUTOFFS[-1] + timedelta(weeks=4),
                ],
            ).fetchall()
        ]

    assert snap["meta"]["weeks"] == {"before": 8, "after": 4}
    assert shown["weeks"] == expected
    assert shown["churned"] == bool(test.y[0])


def test_cli_export_needs_trained_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    cfg = str(REPO_ROOT / "configs" / "train.yaml")

    result = CliRunner().invoke(app, ["export", "-c", cfg])

    assert result.exit_code == 1
