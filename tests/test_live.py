"""`lolret predict`: a live prediction for one player against a fake Riot API."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from conftest import REPO_ROOT
from test_model import config as train_config
from test_model import write_examples
from typer.testing import CliRunner

from lolret.cli import app
from lolret.live.predict import (
    LivePrediction,
    PlayerNotFoundError,
    fetch_live,
    format_prediction,
    predict_cached,
    split_riot_id,
)
from lolret.model.models import Ladder
from lolret.model.train import examples_path, models_dir, train_and_evaluate
from lolret.riot.client import RiotClient

NOW = datetime(2026, 10, 25, 15, 30, tzinfo=UTC)  # the cutoff is 2026-10-25 00:00 UTC
ACCOUNT = r"https://americas\.api\.riotgames\.com/riot/account/v1/accounts/by-riot-id/(?P<name>[^/]+)/(?P<tag>[^/]+)"
MATCH_IDS = (
    r"https://americas\.api\.riotgames\.com/lol/match/v5/matches/by-puuid/(?P<puuid>[^/]+)/ids"
)
MATCH = r"https://americas\.api\.riotgames\.com/lol/match/v5/matches/(?P<match_id>NA1_[^/]+)$"
PUUIDS = {"Active Player": "puuid-active-secret", "Gone": "puuid-gone-secret"}


def account(request: httpx.Request, name: str, tag: str) -> httpx.Response:
    puuid = PUUIDS.get(httpx.URL(f"/{name}").path.strip("/"))
    if puuid is None:
        return httpx.Response(404, json={"status": {"status_code": 404}})
    return httpx.Response(200, json={"puuid": puuid, "gameName": name, "tagLine": tag})


def match_ids(request: httpx.Request, puuid: str) -> httpx.Response:
    start = int(request.url.params["startTime"])
    if puuid == "puuid-gone-secret" and start > NOW.timestamp() - 60 * 86400 + 28 * 86400:
        return httpx.Response(200, json=[])  # nothing in the last 4 weeks
    return httpx.Response(200, json=[f"NA1_{puuid}_{start}_{k}" for k in (1, 0)])


def match(request: httpx.Request, match_id: str) -> httpx.Response:
    _, puuid, start, k = match_id.split("_")
    begin = (int(start) + 7200 * (1 + int(k))) * 1000
    player = {
        "puuid": puuid,
        "win": k == "0",
        "kills": 4,
        "deaths": 3,
        "assists": 6,
        "championId": 7,
        "teamPosition": "BOTTOM",
        "teamId": 100,
        "summonerLevel": 250,
    }
    info = {
        "gameStartTimestamp": begin,
        "gameEndTimestamp": begin + 1_500_000,
        "gameDuration": 1500,
        "queueId": 420,
        "participants": [player],
    }
    return httpx.Response(200, json={"metadata": {"matchId": match_id}, "info": info})


@pytest.fixture
def fake_riot() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.get(url__regex=ACCOUNT, name="account").mock(side_effect=account)
        router.get(url__regex=MATCH_IDS, name="ids").mock(side_effect=match_ids)
        router.get(url__regex=MATCH, name="match").mock(side_effect=match)
        yield router


@pytest.fixture
def ladder(tmp_path: Path) -> Ladder:
    write_examples(examples_path(tmp_path, "synthetic"))
    train_and_evaluate(train_config(), tmp_path)
    return Ladder.load(models_dir(tmp_path, "synthetic"))


async def no_sleep(_: float) -> None:
    return None


def run(riot_id: str, ladder: Ladder, cache: Path) -> LivePrediction:
    async def go() -> tuple[str, datetime]:
        async with httpx.AsyncClient() as http:
            client = RiotClient("k", limits=[(10_000, 1.0)], http=http, sleep=no_sleep)
            return await fetch_live(client, riot_id, "na1", cache, now=NOW)

    puuid, cutoff = asyncio.run(go())
    return predict_cached(puuid, riot_id, "na1", cutoff, ladder, cache)


def test_split_riot_id() -> None:
    assert split_riot_id("Some Name#EUW") == ("Some Name", "EUW")
    assert split_riot_id("a#b#TAG") == ("a#b", "TAG")
    with pytest.raises(ValueError, match="Name#TAG"):
        split_riot_id("NoTag")


def test_a_live_prediction_for_an_active_player(
    fake_riot: respx.MockRouter, ladder: Ladder, tmp_path: Path
) -> None:
    p = run("Active Player#NA1", ladder, tmp_path / "live.sqlite")

    assert p.eligible
    assert p.cutoff == datetime(2026, 10, 25, tzinfo=UTC)
    assert p.churn is not None
    assert 0 < p.churn < 1
    assert len(p.drivers) == 3
    assert p.games_28d == 8  # two games a week
    starts = [int(c.request.url.params["startTime"]) for c in fake_riot["ids"].calls]
    assert max(starts) + 7 * 86400 <= p.cutoff.timestamp()  # no week after the cutoff
    assert "Active%20Player" in str(fake_riot["account"].calls[0].request.url)
    text = format_prediction(p)
    assert "Chance of playing no game in the next 28 days" in text
    assert "secret" not in text  # the puuid is never shown


def test_asking_again_the_same_day_reuses_the_cache(
    fake_riot: respx.MockRouter, ladder: Ladder, tmp_path: Path
) -> None:
    first = run("Active Player#NA1", ladder, tmp_path / "live.sqlite")
    calls = fake_riot["ids"].call_count + fake_riot["match"].call_count

    again = run("Active Player#NA1", ladder, tmp_path / "live.sqlite")

    assert again.churn == pytest.approx(first.churn)
    assert fake_riot["ids"].call_count + fake_riot["match"].call_count == calls


def test_a_player_who_stopped_a_month_ago_is_not_covered(
    fake_riot: respx.MockRouter, ladder: Ladder, tmp_path: Path
) -> None:
    run("Active Player#NA1", ladder, tmp_path / "live.sqlite")  # another player in the cache

    p = run("Gone#NA1", ladder, tmp_path / "live.sqlite")

    assert not p.eligible
    assert p.churn is None
    assert "not covered" in format_prediction(p)


def test_an_unknown_riot_id_is_an_error(
    fake_riot: respx.MockRouter, ladder: Ladder, tmp_path: Path
) -> None:
    with pytest.raises(PlayerNotFoundError):
        run("Nobody#NA1", ladder, tmp_path / "live.sqlite")


def test_cli_predict_needs_trained_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RIOT_API_KEY", "k")
    cfg = str(REPO_ROOT / "configs" / "train.yaml")

    result = CliRunner().invoke(app, ["predict", "--riot-id", "A#B", "-c", cfg])

    assert result.exit_code == 1
