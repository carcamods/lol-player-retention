"""Operational notifications: an optional Discord ping when a long job ends.

This is not error monitoring. Errors are logged and end the process with a non-zero exit code.
A failed ping is logged as a warning and never fails the job.
"""

import httpx
from pydantic import SecretStr

from lolret.log import get_logger

log = get_logger(__name__)


def notify_discord(webhook_url: SecretStr | None, message: str) -> bool:
    """Post `message` to the webhook if one is configured. Returns True if it was delivered."""
    if webhook_url is None:
        return False
    try:
        response = httpx.post(webhook_url.get_secret_value(), json={"content": message}, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # Log only the error type and status: httpx messages include the URL, which holds the token.
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        log.warning("Discord notification failed (%s, status %s)", type(exc).__name__, status)
        return False
    return True
