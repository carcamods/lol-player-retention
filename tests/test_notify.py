import json

import pytest
import respx
from pydantic import SecretStr

from lolret.notify import notify_discord

WEBHOOK = "https://discord.com/api/webhooks/123/secret-token-value"


def test_no_webhook_means_no_request() -> None:
    with respx.mock() as router:
        assert notify_discord(None, "done") is False
    assert router.calls.call_count == 0


def test_posts_the_message() -> None:
    with respx.mock() as router:
        route = router.post(WEBHOOK).respond(204)
        assert notify_discord(SecretStr(WEBHOOK), "run finished") is True

    assert json.loads(route.calls.last.request.content) == {"content": "run finished"}


def test_failure_is_a_warning_and_never_logs_the_token(caplog: pytest.LogCaptureFixture) -> None:
    with respx.mock() as router:
        router.post(WEBHOOK).respond(404)
        assert notify_discord(SecretStr(WEBHOOK), "run finished") is False

    assert "Discord notification failed" in caplog.text
    assert "secret-token-value" not in caplog.text
