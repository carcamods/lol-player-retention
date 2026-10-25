"""Async Riot API client.

- The key travels in the `X-Riot-Token` header, never in the URL, so request URLs are safe
  to log and to use as cache keys.
- One `RateLimiter` per routing value, because Riot's limits are per routing value.
- 404 is a normal answer (e.g. a match that no longer exists) and is returned, not raised.
- 401/403 mean the key is missing, expired or revoked. They raise `RiotAuthError`, which
  should stop a run: retrying cannot fix it.
- 429, 5xx and network errors are retried with backoff (honouring `Retry-After`), then
  raise `RiotRequestError`.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self
from urllib.parse import quote

import httpx

from lolret.log import get_logger
from lolret.riot.ratelimit import RateLimiter, Window
from lolret.riot.routing import base_url

log = get_logger(__name__)

Params = Mapping[str, str | int]

# Riot returns at most 100 match IDs per request.
MAX_MATCH_IDS = 100


class RiotAuthError(Exception):
    """The key was rejected (401/403). Fatal for a run."""


class RiotRequestError(Exception):
    """A request still failed after every retry."""


@dataclass(frozen=True)
class RiotResponse:
    status: int  # 200 or 404
    body: Any  # parsed JSON; None for 404


class RiotEndpoints:
    """The endpoints this project uses, on top of a generic `get`."""

    async def get(self, routing: str, path: str, params: Params | None = None) -> RiotResponse:
        raise NotImplementedError

    async def league_entries(
        self, platform: str, tier: str, division: str, page: int
    ) -> RiotResponse:
        path = f"/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}"
        return await self.get(platform, path, {"page": page})

    async def match_ids(
        self,
        region: str,
        puuid: str,
        *,
        start_time: int,
        end_time: int,
        start: int = 0,
        count: int = MAX_MATCH_IDS,
    ) -> RiotResponse:
        path = f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params = {"startTime": start_time, "endTime": end_time, "start": start, "count": count}
        return await self.get(region, path, params)

    async def match(self, region: str, match_id: str) -> RiotResponse:
        return await self.get(region, f"/lol/match/v5/matches/{match_id}")

    async def account_by_riot_id(self, region: str, game_name: str, tag_line: str) -> RiotResponse:
        """The account (with its puuid) for a Riot ID `game_name#tag_line`; 404 if none."""
        name, tag = quote(game_name, safe=""), quote(tag_line, safe="")
        return await self.get(region, f"/riot/account/v1/accounts/by-riot-id/{name}/{tag}")


class RiotClient(RiotEndpoints):
    def __init__(
        self,
        api_key: str,
        *,
        limits: list[Window],
        http: httpx.AsyncClient | None = None,
        max_attempts: int = 5,
        backoff_base: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._api_key = api_key
        self._limits = limits
        self._http = http or httpx.AsyncClient(timeout=30.0)
        self._owns_http = http is None
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._limiters: dict[str, RateLimiter] = {}
        self.requests_sent = 0

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_http:
            await self._http.aclose()

    def _limiter(self, routing: str) -> RateLimiter:
        if routing not in self._limiters:
            self._limiters[routing] = RateLimiter(self._limits, sleep=self._sleep)
        return self._limiters[routing]

    async def get(self, routing: str, path: str, params: Params | None = None) -> RiotResponse:
        url = base_url(routing) + path
        headers = {"X-Riot-Token": self._api_key}
        error = ""
        for attempt in range(1, self._max_attempts + 1):
            await self._limiter(routing).acquire()
            self.requests_sent += 1
            try:
                response = await self._http.get(url, params=params, headers=headers)
            except httpx.TransportError as exc:
                error = type(exc).__name__
                delay = self._backoff_base * 2 ** (attempt - 1)
            else:
                status = response.status_code
                if status == httpx.codes.OK:
                    return RiotResponse(status, response.json())
                if status == httpx.codes.NOT_FOUND:
                    return RiotResponse(status, None)
                if status in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
                    raise RiotAuthError(
                        f"HTTP {status} from {routing}{path}: the Riot API key was rejected. "
                        "Check RIOT_API_KEY in .env (expired, revoked or mistyped)."
                    )
                error = f"HTTP {status}"
                delay = self._backoff_base * 2 ** (attempt - 1)
                if status == httpx.codes.TOO_MANY_REQUESTS:
                    delay = float(response.headers.get("Retry-After", delay))
                    limit_type = response.headers.get("X-Rate-Limit-Type", "unknown")
                    log.warning(
                        "429 from %s (%s limit), waiting %.0f s", routing, limit_type, delay
                    )
            if attempt < self._max_attempts:
                log.debug("%s on %s%s, retry %d in %.1f s", error, routing, path, attempt, delay)
                await self._sleep(delay)
        raise RiotRequestError(
            f"GET {routing}{path} failed after {self._max_attempts} attempts ({error})"
        )
