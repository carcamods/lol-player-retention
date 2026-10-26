"""Collection for a forward test, in two phases with a store each (ADR 0011).

- Features (`data/raw/<name>.sqlite`): for every player of the base run, the weekly match lists
  before the cutoff and details of the most recent matches. Most of it is already in the base
  run's store, which is read and never written.
- Labels (`data/raw/<name>-labels.sqlite`): once the label window has fully happened, the
  weekly match lists inside it, only for the players with frozen predictions.

Each phase has its own store, so each tracks its own completed players, and the labels store
not existing proves that no outcome was collected before the predictions were frozen.
"""

import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from lolret.collect.cache import CachedRiot
from lolret.collect.history import bucket_match_ids, recent_before
from lolret.collect.runner import (
    CollectOne,
    PlatformResult,
    RunResult,
    collect_players,
    per_platform,
)
from lolret.collect.store import LayeredStore, Store
from lolret.forward.config import Forward, ForwardError
from lolret.riot.client import RiotClient
from lolret.riot.routing import region_for


def base_store_path(data_dir: Path, fwd: Forward) -> Path:
    return data_dir / "raw" / f"{fwd.base.run_name}.sqlite"


def features_store_path(data_dir: Path, fwd: Forward) -> Path:
    return data_dir / "raw" / f"{fwd.name}.sqlite"


def labels_store_path(data_dir: Path, fwd: Forward) -> Path:
    return data_dir / "raw" / f"{fwd.name}-labels.sqlite"


def open_base(data_dir: Path, fwd: Forward) -> Store:
    path = base_store_path(data_dir, fwd)
    if not path.exists():
        raise ForwardError(f"the base run '{fwd.base.run_name}' has no data at {path}")
    return Store(path, read_only=True)


def open_features(data_dir: Path, fwd: Forward, base: Store, *, read_only: bool) -> LayeredStore:
    path = features_store_path(data_dir, fwd)
    if read_only and not path.exists():
        raise ForwardError(f"no forward features at {path}: run `lolret forward collect` first")
    return LayeredStore(path, [base], read_only=read_only)


def copy_players(
    source: Store, target: Store, platforms: list[str], only: set[str] | None = None
) -> None:
    """Register the source's complete players in the target, keeping existing completion.

    `only` limits it to these "platform:puuid" keys.
    """
    for platform in platforms:
        groups: dict[tuple[str, str], list[str]] = defaultdict(list)
        for p in source.players(platform):
            if p.complete and (only is None or f"{platform}:{p.puuid}" in only):
                groups[(p.tier, p.division)].append(p.puuid)
        for (tier, division), puuids in groups.items():
            target.add_players(platform, tier, division, puuids)


def require_complete(store: Store, platforms: list[str], what: str) -> None:
    """Fail unless every player in the store is complete and no request failure is open."""
    incomplete = sum(not p.complete for platform in platforms for p in store.players(platform))
    failures = store.summary()["failures"]["open"]
    if incomplete or failures:
        raise ForwardError(
            f"the {what} collection isn't finished ({incomplete} players incomplete, {failures} "
            f"failed requests): re-run it first"
        )


async def _run(
    store: Store, client: RiotClient, platforms: list[str], one: CollectOne
) -> RunResult:
    riot = CachedRiot(client, store)
    started = time.monotonic()

    async def work(platform: str) -> PlatformResult:
        return await collect_players(riot, store, platform, one, progress_every=100)

    results = await per_platform(platforms, work)
    return RunResult(results, riot.misses, riot.hits, time.monotonic() - started)


async def collect_features(
    fwd: Forward, data_dir: Path, client: RiotClient, *, now: datetime
) -> RunResult:
    """Weekly match lists before the cutoff and the latest match details, for every player."""
    if fwd.cutoff > now:
        raise ForwardError(f"the cutoff {fwd.cutoff:%Y-%m-%d} hasn't happened yet")
    if labels_store_path(data_dir, fwd).exists():
        raise ForwardError("labels were already collected; the features phase is closed")
    buckets = fwd.feature_buckets

    async def one(riot: CachedRiot, platform: str, puuid: str) -> None:
        region = region_for(platform)
        ids = [await bucket_match_ids(riot, region, puuid, b) for b in buckets]
        for match_id in recent_before(buckets, ids, fwd.cutoff, fwd.collect.details_per_cutoff):
            await riot.match(region, match_id)

    base = open_base(data_dir, fwd)
    store = open_features(data_dir, fwd, base, read_only=False)
    try:
        copy_players(base, store, fwd.collect.platforms)
        return await _run(store, client, fwd.collect.platforms, one)
    finally:
        store.close()
        base.close()


async def collect_labels(
    fwd: Forward, data_dir: Path, client: RiotClient, players: set[str], *, now: datetime
) -> RunResult:
    """Weekly match lists inside the label window, for the players with frozen predictions."""
    if fwd.label_window_end > now:
        raise ForwardError(
            f"the label window ends {fwd.label_window_end:%Y-%m-%d %H:%M} UTC, in the future"
        )
    buckets = fwd.label_buckets

    async def one(riot: CachedRiot, platform: str, puuid: str) -> None:
        region = region_for(platform)
        for bucket in buckets:
            await bucket_match_ids(riot, region, puuid, bucket)

    base = open_base(data_dir, fwd)
    features = open_features(data_dir, fwd, base, read_only=True)
    store = LayeredStore(labels_store_path(data_dir, fwd), [features, base])
    try:
        copy_players(base, store, fwd.collect.platforms, only=players)
        return await _run(store, client, fwd.collect.platforms, one)
    finally:
        store.close()
        features.close()
        base.close()
