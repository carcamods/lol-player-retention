"""Match history for one player.

1. Match IDs for every time bucket in the run's range. Cheap (usually one request per bucket),
   and they give per-week activity before each cutoff and the label after it.
2. Full details for the `details_per_cutoff` most recent matches before each cutoff. Matches
   shared between cutoffs are fetched once, thanks to the cache.
"""

from datetime import datetime

from lolret.collect.config import Bucket, CollectConfig
from lolret.riot.client import MAX_MATCH_IDS, RiotEndpoints
from lolret.riot.routing import region_for


async def bucket_match_ids(
    riot: RiotEndpoints, region: str, puuid: str, bucket: Bucket
) -> list[str]:
    """All match IDs that started in [start, end), newest first."""
    start, end = bucket
    ids: list[str] = []
    offset = 0
    while True:
        response = await riot.match_ids(
            region,
            puuid,
            start_time=int(start.timestamp()),
            end_time=int(end.timestamp()) - 1,  # Riot's endTime is inclusive
            start=offset,
        )
        page: list[str] = response.body if response.status == 200 else []
        ids.extend(page)
        if len(page) < MAX_MATCH_IDS:
            return ids
        offset += MAX_MATCH_IDS


def recent_before(
    buckets: list[Bucket], ids_per_bucket: list[list[str]], cutoff: datetime, n: int
) -> list[str]:
    """The n most recent match IDs from buckets ending at or before `cutoff`, newest first."""
    recent: list[str] = []
    for (_, end), ids in reversed(list(zip(buckets, ids_per_bucket, strict=True))):
        if end <= cutoff:
            recent.extend(ids)
            if len(recent) >= n:
                break
    return recent[:n]


async def collect_player(
    riot: RiotEndpoints, cfg: CollectConfig, platform: str, puuid: str
) -> None:
    region = region_for(platform)
    ids_per_bucket = [await bucket_match_ids(riot, region, puuid, b) for b in cfg.buckets]
    for cutoff in cfg.cutoffs:
        for match_id in recent_before(cfg.buckets, ids_per_bucket, cutoff, cfg.details_per_cutoff):
            await riot.match(region, match_id)
