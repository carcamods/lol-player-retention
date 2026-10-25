"""Turn a collection run's stored responses into three tables.

- `players`: the sampled players whose collection finished.
- `buckets`: games started per player per time bucket (from match-ID lists).
- `matches`: one row per (player, match) for every match whose details were fetched.

Reading goes through the same endpoint helpers as collection, against the store only, so the
keys match exactly and building never calls the API. Timestamps are naive UTC.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pyarrow as pa

from lolret.collect.cache import cache_key
from lolret.collect.config import CollectConfig
from lolret.collect.history import bucket_match_ids
from lolret.collect.store import Store
from lolret.riot.client import Params, RiotEndpoints, RiotResponse
from lolret.riot.routing import region_for

PLAYERS_SCHEMA = pa.schema(
    [
        ("platform", pa.string()),
        ("puuid", pa.string()),
        ("tier", pa.string()),
        ("division", pa.string()),
    ]
)
BUCKETS_SCHEMA = pa.schema(
    [
        ("platform", pa.string()),
        ("puuid", pa.string()),
        ("bucket_start", pa.timestamp("ms")),
        ("bucket_end", pa.timestamp("ms")),
        ("games", pa.int32()),
    ]
)
MATCHES_SCHEMA = pa.schema(
    [
        ("platform", pa.string()),
        ("puuid", pa.string()),
        ("match_id", pa.string()),
        ("game_start", pa.timestamp("ms")),
        ("game_end", pa.timestamp("ms")),
        ("queue_id", pa.int32()),
        ("duration_s", pa.int32()),
        ("win", pa.bool_()),
        ("kills", pa.int32()),
        ("deaths", pa.int32()),
        ("assists", pa.int32()),
        ("champion_id", pa.int32()),
        ("team_position", pa.string()),
        ("remake", pa.bool_()),
        ("surrendered", pa.bool_()),
    ]
)


class NotStoredError(LookupError):
    """The response was never collected (e.g. the player's collection hasn't finished)."""


class StoredOnly(RiotEndpoints):
    """Answers from the store; never touches the network."""

    def __init__(self, store: Store) -> None:
        self._store = store

    async def get(self, routing: str, path: str, params: Params | None = None) -> RiotResponse:
        response = self._store.get(cache_key(routing, path, params))
        if response is None:
            raise NotStoredError(f"{routing}{path} is not in the store")
        return response


@dataclass(frozen=True)
class Tables:
    players: pa.Table
    buckets: pa.Table
    matches: pa.Table


def utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC).replace(tzinfo=None)


def participant_row(platform: str, puuid: str, match: dict[str, Any]) -> dict[str, Any] | None:
    """The player's row in one match, or None if they aren't in it."""
    info = match["info"]
    player = next((p for p in info["participants"] if p.get("puuid") == puuid), None)
    if player is None:
        return None
    start = info["gameStartTimestamp"]
    end = info.get("gameEndTimestamp") or start + info["gameDuration"] * 1000
    return {
        "platform": platform,
        "puuid": puuid,
        "match_id": match["metadata"]["matchId"],
        "game_start": utc(start),
        "game_end": utc(end),
        "queue_id": info["queueId"],
        "duration_s": info["gameDuration"],
        "win": bool(player["win"]),
        "kills": player["kills"],
        "deaths": player["deaths"],
        "assists": player["assists"],
        "champion_id": player["championId"],
        "team_position": player.get("teamPosition") or None,  # empty outside Summoner's Rift
        "remake": bool(player.get("gameEndedInEarlySurrender", False)),
        "surrendered": bool(player.get("gameEndedInSurrender", False)),
    }


async def _extract(store: Store, cfg: CollectConfig, until: datetime | None) -> Tables:
    reader = StoredOnly(store)
    players: list[dict[str, Any]] = []
    buckets: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    for platform in cfg.platforms:
        region = region_for(platform)
        for player in store.players(platform):
            if not player.complete:
                continue
            players.append(
                {
                    "platform": platform,
                    "puuid": player.puuid,
                    "tier": player.tier,
                    "division": player.division,
                }
            )
            for start, end in cfg.buckets:
                if until is not None and end > until:
                    continue  # not collected yet (a forward test before its label window)
                ids = await bucket_match_ids(reader, region, player.puuid, (start, end))
                buckets.append(
                    {
                        "platform": platform,
                        "puuid": player.puuid,
                        "bucket_start": start.replace(tzinfo=None),
                        "bucket_end": end.replace(tzinfo=None),
                        "games": len(ids),
                    }
                )
                for match_id in ids:
                    try:
                        response = await reader.match(region, match_id)
                    except (
                        NotStoredError
                    ):  # only the most recent matches before each cutoff are fetched
                        continue
                    if response.status == 200:
                        row = participant_row(platform, player.puuid, response.body)
                        if row is not None:
                            matches.append(row)
    return Tables(
        players=pa.Table.from_pylist(players, PLAYERS_SCHEMA),
        buckets=pa.Table.from_pylist(buckets, BUCKETS_SCHEMA),
        matches=pa.Table.from_pylist(matches, MATCHES_SCHEMA),
    )


def extract(store: Store, cfg: CollectConfig, *, until: datetime | None = None) -> Tables:
    """Tables for the run's complete players. With `until`, only buckets ending by then."""
    return asyncio.run(_extract(store, cfg, until))
