from pathlib import Path

import pytest
from conftest import REPO_ROOT
from typer.testing import CliRunner

from lolret.cli import app
from lolret.collect.store import Store

PILOT = str(REPO_ROOT / "configs" / "collect-pilot.yaml")


def test_collect_without_a_key_exits_with_an_error() -> None:
    result = CliRunner().invoke(app, ["collect", "-c", PILOT])

    assert result.exit_code == 1


def test_status_before_any_run() -> None:
    result = CliRunner().invoke(app, ["status", "-c", PILOT])

    assert result.exit_code == 0
    assert "no data yet" in result.stdout


def test_status_reports_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    store = Store(tmp_path / "data" / "raw" / "pilot.sqlite")
    store.add_players("na1", "GOLD", "II", ["p1", "p2"])
    store.mark_complete("na1", "p1")
    store.close()

    result = CliRunner().invoke(app, ["status", "-c", PILOT])

    assert result.exit_code == 0
    assert "1 / 2" in result.stdout
    assert "target 15" in result.stdout
