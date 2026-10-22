"""Smoke tests for the project foundation: config, logging and the CLI."""

import logging

import pytest
from typer.testing import CliRunner

from lolret import __version__
from lolret.cli import app
from lolret.config import Settings
from lolret.log import configure_logging, get_logger

FAKE_KEY = "fake-riot-key-for-tests"


def test_secret_is_read_from_env_but_never_rendered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RIOT_API_KEY", FAKE_KEY)
    settings = Settings()

    assert settings.riot_api_key is not None
    assert settings.riot_api_key.get_secret_value() == FAKE_KEY
    assert FAKE_KEY not in repr(settings)
    assert FAKE_KEY not in str(settings.model_dump())


def test_cli_config_reports_secret_state_without_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RIOT_API_KEY", FAKE_KEY)

    result = CliRunner().invoke(app, ["config"])

    assert result.exit_code == 0
    assert "riot_api_key:        set" in result.stdout
    assert "discord_webhook_url: missing" in result.stdout
    assert FAKE_KEY not in result.stdout


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_log_format(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    get_logger("riot.client").info("hello")

    line = capsys.readouterr().err.strip()
    assert line.endswith("[lolret.riot.client] [INFO] hello")
    assert line[:4].isdigit()  # starts with the UTC timestamp
    assert get_logger("lolret.cli").name == "lolret.cli"
    assert logging.getLogger("lolret").level == logging.INFO
