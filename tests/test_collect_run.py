"""End-to-end collection against a fake Riot API (respx): sampling, history, caching, resume."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx

from lolret.collect.config import CollectConfig
from lolret.collect.runner import RunResult, run_collection
from lolret.collect.store import Store
from lolret.riot.client import RiotAuthError, RiotClient

NOW = datetime(2026, 10, 23, tzinfo=UTC)
ENTRIES = r"https://na1\.api\.riotgames\.com/lol/league/v4/entries/RANKED_SOLO_5x5/(?P<tier>\w+)/(?P<division>\w+)"
MATCH_IDS = (
    r"https://americas\.api\.riotgames\.com/lol/match/v5/matches/by-puuid/(?P<puuid>[^/]+)/ids"
)
MATCH = r"https://americas\.api\.riotgames\.com/lol/match/v5/matches/(?P<match_id>NA1_[^/]+)$"

CONFIG = CollectConfig.model_validate(
    {
        "run_name": "test",
        "platforms": ["na1"],
        "tiers": ["GOLD"],
        "divisions": ["II"],
        "players_per_division": 3,
        "pages_per_division": 2,
        "season_start": "2026-01-08",
        "latest_cutoff": "2026-09-24",
        "n_cutoffs": 3,
        "cutoff_spacing_days": 28,
        "lookback_days": 56,
        "label_window_days": 28,
        "bucket_days": 7,
        "details_per_cutoff": 3,
        "seed": 7,
    }
)


def entries(request: httpx.Request, tier: str, division: str) -> httpx.Response:
    page = int(request.url.params["page"])
    if page > 3:  # the division has 3 pages of 4 players
        return httpx.Response(200, json=[])
    players = [
        {"puuid": f"{tier}-{division}-{page}-{i}", "tier": tier, "rank": division} for i in range(4)
    ]
    return httpx.Response(200, json=players)


def match_ids(request: httpx.Request, puuid: str) -> httpx.Response:
    start_time = request.url.params["startTime"]
    return httpx.Response(200, json=[f"NA1_{puuid}_{start_time}_{k}" for k in (2, 1)])


def match(request: httpx.Request, match_id: str) -> httpx.Response:
    return httpx.Response(200, json={"metadata": {"matchId": match_id}})


@pytest.fixture
def fake_riot() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.get(url__regex=ENTRIES, name="entries").mock(side_effect=entries)
        router.get(url__regex=MATCH_IDS, name="ids").mock(side_effect=match_ids)
        router.get(url__regex=MATCH, name="match").mock(side_effect=match)
        yield router


async def no_sleep(_: float) -> None:
    return None


async def run(store: Store, max_attempts: int = 5, cfg: CollectConfig = CONFIG) -> RunResult:
    async with httpx.AsyncClient() as http:
        client = RiotClient(
            "k", limits=[(10_000, 1.0)], http=http, max_attempts=max_attempts, sleep=no_sleep
        )
        return await run_collection(cfg, store, client, now=NOW)


@pytest.mark.anyio
async def test_full_run_then_rerun_sends_no_new_requests(
    fake_riot: respx.MockRouter, tmp_path: Path
) -> None:
    store = Store(tmp_path / "run.sqlite")

    first = await run(store)

    [platform] = first.platforms
    assert (platform.players, platform.complete, platform.failed) == (3, 3, 0)
    # 20 weekly buckets per player; 3 cutoffs x 3 most recent matches, none shared.
    assert fake_riot["ids"].call_count == 3 * 20
    assert fake_riot["match"].call_count == 3 * 9
    calls_before = fake_riot.calls.call_count

    second = await run(store)  # complete players are skipped outright

    assert (second.requests, second.cache_hits) == (0, 0)
    assert fake_riot.calls.call_count == calls_before


@pytest.mark.anyio
async def test_interrupted_players_resume_from_the_cache(
    fake_riot: respx.MockRouter, tmp_path: Path
) -> None:
    path = tmp_path / "run.sqlite"
    store = Store(path)
    await run(store)
    calls_before = fake_riot.calls.call_count
    # Simulate a crash after the requests were stored but before players were marked complete.
    with sqlite3.connect(path) as db:
        db.execute("UPDATE players SET complete_at = NULL")

    resumed = await run(store)

    assert resumed.requests == 0
    assert resumed.cache_hits == 3 * (20 + 9)
    assert resumed.platforms[0].complete == 3
    assert fake_riot.calls.call_count == calls_before


@pytest.mark.anyio
async def test_sample_is_reproducible(fake_riot: respx.MockRouter, tmp_path: Path) -> None:
    store_a = Store(tmp_path / "a.sqlite")
    store_b = Store(tmp_path / "b.sqlite")

    await run(store_a)
    await run(store_b)

    assert [p.puuid for p in store_a.players("na1")] == [p.puuid for p in store_b.players("na1")]


@pytest.mark.anyio
async def test_raising_the_target_keeps_existing_players_and_adds_more(
    fake_riot: respx.MockRouter, tmp_path: Path
) -> None:
    store = Store(tmp_path / "run.sqlite")
    await run(store)
    first = {p.puuid for p in store.players("na1")}
    calls_before = fake_riot["ids"].call_count

    bigger = await run(store, cfg=CONFIG.model_copy(update={"players_per_division": 5}))

    after = {p.puuid for p in store.players("na1")}
    assert first < after
    assert len(after) == 5
    assert bigger.platforms[0].complete == 5
    # Only the 2 new players' histories were requested.
    assert fake_riot["ids"].call_count - calls_before == 2 * 20


@pytest.mark.anyio
async def test_failed_player_is_retried_on_the_next_run(
    fake_riot: respx.MockRouter, tmp_path: Path
) -> None:
    store = Store(tmp_path / "run.sqlite")
    healthy = fake_riot["ids"].side_effect

    def broken_for_one_player(request: httpx.Request, puuid: str) -> httpx.Response:
        if puuid == store.players("na1")[0].puuid:
            return httpx.Response(503)
        return httpx.Response(200, json=[])

    fake_riot["ids"].side_effect = broken_for_one_player
    first = await run(store, max_attempts=2)
    assert (first.platforms[0].complete, first.failed) == (2, 1)
    assert store.summary()["failures"]["open"] == 1

    fake_riot["ids"].side_effect = healthy
    second = await run(store, max_attempts=2)
    assert (second.platforms[0].complete, second.failed) == (3, 0)
    assert store.summary()["failures"]["open"] == 0


@pytest.mark.anyio
async def test_rejected_key_stops_the_run(fake_riot: respx.MockRouter, tmp_path: Path) -> None:
    fake_riot["entries"].side_effect = None
    fake_riot["entries"].return_value = httpx.Response(401)

    with pytest.raises(RiotAuthError):
        await run(Store(tmp_path / "run.sqlite"))


@pytest.mark.anyio
async def test_refuses_to_run_before_label_windows_end(tmp_path: Path) -> None:
    async with httpx.AsyncClient() as http:
        client = RiotClient("k", limits=[(10, 1.0)], http=http)
        with pytest.raises(ValueError, match="in the future"):
            await run_collection(
                CONFIG,
                Store(tmp_path / "run.sqlite"),
                client,
                now=datetime(2026, 10, 1, tzinfo=UTC),
            )
