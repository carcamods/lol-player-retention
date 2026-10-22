import logging
from pathlib import Path

import pytest

from lolret.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Run every test from an empty directory, so a developer's real .env is never read.
    monkeypatch.chdir(tmp_path)
    for var in ("RIOT_API_KEY", "RIOT_RATE_LIMITS", "DISCORD_WEBHOOK_URL", "DATA_DIR", "LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    # CliRunner swaps stderr per invocation; drop handlers bound to a previous test's stream.
    logging.getLogger("lolret").handlers.clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
