"""Run a collection: sample players on each platform, then fetch every player's history.

Platforms run concurrently, because their routing values have separate rate limits. Within a
platform, work is sequential: the rate limit, not latency, is the bottleneck. A failed player
is logged and retried on the next run. A rejected key stops everything.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from lolret.collect.cache import CachedRiot
from lolret.collect.config import CollectConfig
from lolret.collect.history import collect_player
from lolret.collect.ladder import sample_division
from lolret.collect.store import Store
from lolret.log import get_logger
from lolret.riot.client import RiotAuthError, RiotClient, RiotRequestError

log = get_logger(__name__)


@dataclass(frozen=True)
class PlatformResult:
    platform: str
    players: int
    complete: int
    failed: int


@dataclass(frozen=True)
class RunResult:
    platforms: list[PlatformResult]
    requests: int
    cache_hits: int
    seconds: float

    @property
    def failed(self) -> int:
        return sum(p.failed for p in self.platforms)


# Fetches everything one player needs: (riot, platform, puuid).
CollectOne = Callable[[CachedRiot, str, str], Awaitable[None]]


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    return f"{minutes // 60}h{minutes % 60:02d}m"


async def collect_platform(
    riot: CachedRiot, store: Store, cfg: CollectConfig, platform: str, *, progress_every: int = 25
) -> PlatformResult:
    failed = 0
    for tier in cfg.tiers:
        for division in cfg.divisions:
            # Below target: sample (again). Pages are cached, so a top-up only costs new pages.
            if store.count_players(platform, tier, division) >= cfg.players_per_division:
                continue
            try:
                puuids = await sample_division(riot, cfg, platform, tier, division)
            except RiotRequestError as exc:
                failed += 1
                log.error(
                    "[%s] sampling %s %s failed, retried next run: %s",
                    platform,
                    tier,
                    division,
                    exc,
                )
                continue
            before = store.count_players(platform, tier, division)
            store.add_players(platform, tier, division, puuids)
            added = store.count_players(platform, tier, division) - before
            if added:
                log.info("[%s] sampled %d players from %s %s", platform, added, tier, division)

    async def one(riot: CachedRiot, platform: str, puuid: str) -> None:
        await collect_player(riot, cfg, platform, puuid)

    return await collect_players(
        riot, store, platform, one, failed=failed, progress_every=progress_every
    )


async def collect_players(
    riot: CachedRiot,
    store: Store,
    platform: str,
    collect_one: CollectOne,
    *,
    failed: int = 0,
    progress_every: int = 25,
) -> PlatformResult:
    """Run `collect_one` for every player of the platform not yet marked complete."""
    players = store.players(platform)
    todo = [p for p in players if not p.complete]
    log.info("[%s] %d players sampled, %d still to collect", platform, len(players), len(todo))
    started = time.monotonic()
    for i, player in enumerate(todo, 1):
        try:
            await collect_one(riot, platform, player.puuid)
        except RiotRequestError as exc:
            failed += 1
            log.error("[%s] player %d/%d failed, retried next run: %s", platform, i, len(todo), exc)
        else:
            store.mark_complete(platform, player.puuid)
        if i % progress_every == 0 or i == len(todo):
            elapsed = time.monotonic() - started
            eta = elapsed / i * (len(todo) - i)
            log.info(
                "[%s] %d/%d players, elapsed %s, about %s left",
                platform,
                i,
                len(todo),
                format_duration(elapsed),
                format_duration(eta),
            )

    complete = sum(p.complete for p in store.players(platform))
    return PlatformResult(platform, len(players), complete, failed)


async def per_platform(
    platforms: list[str], work: Callable[[str], Coroutine[Any, Any, PlatformResult]]
) -> list[PlatformResult]:
    """Run `work` for every platform concurrently. A rejected key surfaces as itself."""
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(work(platform)) for platform in platforms]
    except BaseExceptionGroup as errors:
        # Surface a rejected key as itself rather than wrapped in a group.
        auth = [e for e in errors.exceptions if isinstance(e, RiotAuthError)]
        if auth:
            raise auth[0] from None
        raise
    return [t.result() for t in tasks]


async def run_collection(
    cfg: CollectConfig, store: Store, client: RiotClient, *, now: datetime
) -> RunResult:
    cfg.require_complete_label_windows(now)
    riot = CachedRiot(client, store)
    started = time.monotonic()

    async def work(platform: str) -> PlatformResult:
        return await collect_platform(riot, store, cfg, platform)

    return RunResult(
        platforms=await per_platform(cfg.platforms, work),
        requests=riot.misses,
        cache_hits=riot.hits,
        seconds=time.monotonic() - started,
    )
