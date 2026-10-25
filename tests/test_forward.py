"""Forward test end to end against a fake Riot API: collect, freeze, collect labels, score.

The base run is collected first with the ordinary collector. The forward phases must reuse its
cache (no repeated request), never write its store, and refuse to run out of order.
"""

import asyncio
import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
import yaml
from conftest import REPO_ROOT
from test_model import config as train_config
from test_model import write_examples
from test_nn import nn_config, write_sequences
from typer.testing import CliRunner

from lolret.cli import app
from lolret.collect.config import CollectConfig
from lolret.collect.runner import run_collection
from lolret.collect.store import Store
from lolret.forward.collect import (
    LayeredStore,
    base_store_path,
    collect_features,
    collect_labels,
    labels_store_path,
)
from lolret.forward.config import Forward, ForwardError, load_forward
from lolret.forward.predict import (
    entry_path,
    freeze_predictions,
    frozen_players,
    read_entry,
)
from lolret.forward.score import REPORT_FILE, score_forward
from lolret.model.train import examples_path
from lolret.nn.data import sequences_path
from lolret.nn.forward import freeze_nn_entry
from lolret.riot.client import RiotClient, RiotResponse

CUTOFF = datetime(2026, 10, 22, tzinfo=UTC)
LABEL_END = datetime(2026, 11, 19, tzinfo=UTC)
ENTRIES = r"https://na1\.api\.riotgames\.com/lol/league/v4/entries/RANKED_SOLO_5x5/(?P<tier>\w+)/(?P<division>\w+)"
MATCH_IDS = (
    r"https://americas\.api\.riotgames\.com/lol/match/v5/matches/by-puuid/(?P<puuid>[^/]+)/ids"
)
MATCH = r"https://americas\.api\.riotgames\.com/lol/match/v5/matches/(?P<match_id>NA1_[^/]+)$"

BASE: dict[str, Any] = {
    "run_name": "base",
    "platforms": ["na1"],
    "tiers": ["GOLD"],
    "divisions": ["II"],
    "players_per_division": 24,
    "pages_per_division": 6,
    "season_start": "2026-01-08",
    "latest_cutoff": "2026-09-24",
    "n_cutoffs": 1,
    "cutoff_spacing_days": 28,
    "lookback_days": 56,
    "label_window_days": 28,
    "bucket_days": 7,
    "details_per_cutoff": 5,
    "seed": 7,
}


def index(puuid: str) -> int:
    _, _, page, i = puuid.split("-")
    return int(page) * 4 + int(i)


def games_in_week(puuid: str, start: int) -> int:
    """Every third player quits at the forward cutoff; every fourth took the month before off."""
    n, t = index(puuid), datetime.fromtimestamp(start, UTC)
    if n % 3 == 0 and t >= CUTOFF:
        return 0
    if n % 4 == 0 and datetime(2026, 9, 24, tzinfo=UTC) <= t < CUTOFF:
        return 0
    return (n + start // 604800) % 3


def entries(request: httpx.Request, tier: str, division: str) -> httpx.Response:
    page = int(request.url.params["page"])
    if page > 6:
        return httpx.Response(200, json=[])
    players = [
        {"puuid": f"{tier}{division}-x-{page}-{i}", "tier": tier, "rank": division}
        for i in range(4)
    ]
    return httpx.Response(200, json=players)


def match_ids(request: httpx.Request, puuid: str) -> httpx.Response:
    start = int(request.url.params["startTime"])
    ids = [f"NA1_{puuid}_{start}_{k}" for k in range(games_in_week(puuid, start))]
    return httpx.Response(200, json=list(reversed(ids)))


def match(request: httpx.Request, match_id: str) -> httpx.Response:
    _, puuid, start, k = match_id.split("_")
    begin = (int(start) + 3600 * (1 + int(k))) * 1000
    player = {
        "puuid": puuid,
        "win": int(k) % 2 == 0,
        "kills": 3,
        "deaths": 2,
        "assists": 5,
        "championId": 10 + int(k),
        "teamPosition": "MIDDLE",
    }
    info = {
        "gameStartTimestamp": begin,
        "gameEndTimestamp": begin + 1_800_000,
        "gameDuration": 1800,
        "queueId": 420,
        "participants": [player],
    }
    return httpx.Response(200, json={"metadata": {"matchId": match_id}, "info": info})


@pytest.fixture
def fake_riot() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.get(url__regex=ENTRIES, name="entries").mock(side_effect=entries)
        router.get(url__regex=MATCH_IDS, name="ids").mock(side_effect=match_ids)
        router.get(url__regex=MATCH, name="match").mock(side_effect=match)
        yield router


async def no_sleep(_: float) -> None:
    return None


def client(http: httpx.AsyncClient) -> RiotClient:
    return RiotClient("k", limits=[(10_000, 1.0)], http=http, max_attempts=2, sleep=no_sleep)


def write_configs(root: Path, entries: dict[str, str] | None = None) -> Path:
    (root / "collect.yaml").write_text(yaml.safe_dump(BASE), encoding="utf-8")
    train = train_config(dataset="base").model_dump()
    (root / "train.yaml").write_text(yaml.safe_dump(train), encoding="utf-8")
    forward = {
        "name": "fwd",
        "base_run": str(root / "collect.yaml"),
        "train": str(root / "train.yaml"),
        "cutoff": "2026-10-22",
        "entries": entries or {},
    }
    path = root / "forward.yaml"
    path.write_text(yaml.safe_dump(forward), encoding="utf-8")
    return path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def world(tmp_path: Path, fake_riot: respx.MockRouter) -> tuple[Forward, Path]:
    """A collected base run, its (synthetic) training examples and a forward config."""

    async def collect_base() -> None:
        store = Store(tmp_path / "data" / "raw" / "base.sqlite")
        async with httpx.AsyncClient() as http:
            cfg = CollectConfig.model_validate(BASE)
            await run_collection(cfg, store, client(http), now=CUTOFF)
        store.close()

    asyncio.run(collect_base())
    write_examples(examples_path(tmp_path / "data", "base"))
    return load_forward(write_configs(tmp_path)), tmp_path / "data"


def run_features(fwd: Forward, data_dir: Path, now: datetime) -> Any:
    async def go() -> Any:
        async with httpx.AsyncClient() as http:
            return await collect_features(fwd, data_dir, client(http), now=now)

    return asyncio.run(go())


def run_labels(fwd: Forward, data_dir: Path, now: datetime) -> Any:
    async def go() -> Any:
        async with httpx.AsyncClient() as http:
            players = frozen_players(fwd, data_dir)
            return await collect_labels(fwd, data_dir, client(http), players, now=now)

    return asyncio.run(go())


def requested_starts(router: respx.MockRouter) -> list[datetime]:
    return [
        datetime.fromtimestamp(int(call.request.url.params["startTime"]), UTC)
        for call in router["ids"].calls
    ]


def test_the_repo_forward_config_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)  # the config's paths are relative to the repo root
    fwd = load_forward(REPO_ROOT / "configs" / "forward.yaml")

    assert fwd.cutoff == CUTOFF
    assert fwd.cutoff >= fwd.base.range_end  # every training label is known at the cutoff
    assert len(fwd.feature_buckets) == 8
    assert len(fwd.label_buckets) == 4
    assert set(fwd.feature_buckets) <= set(fwd.base.buckets)  # all cached by run v1


@pytest.mark.parametrize(
    ("cutoff", "message"),
    [("2026-10-25", "bucket grid"), ("2026-09-24", "label window")],
)
def test_config_rejects_an_off_grid_or_early_cutoff(
    tmp_path: Path, cutoff: str, message: str
) -> None:
    path = write_configs(tmp_path)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) | {"cutoff": cutoff}
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_forward(path)


def test_layered_store_reads_through_and_writes_only_its_own_file(tmp_path: Path) -> None:
    base = Store(tmp_path / "base.sqlite")
    base.put("k1", "match", RiotResponse(200, {"a": 1}))
    layered = LayeredStore(tmp_path / "top.sqlite", [base])
    layered.put("k2", "match", RiotResponse(200, {"b": 2}))

    assert layered.get("k1") == RiotResponse(200, {"a": 1})
    assert layered.get("k2") == RiotResponse(200, {"b": 2})
    assert layered.get("missing") is None
    assert base.get("k2") is None


def test_forward_test_end_to_end(world: tuple[Forward, Path], fake_riot: respx.MockRouter) -> None:
    fwd, data_dir = world
    base_before = file_hash(base_store_path(data_dir, fwd))
    fake_riot.reset()  # forget the base run's calls

    # Labels can't be collected before predictions are frozen and committed.
    with pytest.raises(ForwardError, match="no frozen entries"):
        run_labels(fwd, data_dir, LABEL_END)

    result = run_features(fwd, data_dir, datetime(2026, 10, 25, tzinfo=UTC))

    assert result.failed == 0
    assert fake_riot["ids"].call_count == 0  # every weekly list came from the base run's cache
    assert fake_riot["match"].call_count > 0  # only the latest details were new
    assert file_hash(base_store_path(data_dir, fwd)) == base_before

    summary = freeze_predictions(fwd, data_dir, now=datetime(2026, 10, 25, tzinfo=UTC))
    players, preds = read_entry(summary.entry)

    everyone = {f"na1:GOLDII-x-{page}-{i}" for page in range(1, 7) for i in range(4)}
    eligible = set(players.tolist())
    # Everyone played in the month before the cutoff except every fourth player.
    assert eligible == {p for p in everyone if index(p.split(":")[1]) % 4 != 0}
    assert set(preds) == {"majority", "recency", "logreg", "lightgbm"}
    assert summary.sha256 == file_hash(summary.entry)
    with pytest.raises(ForwardError, match="already frozen"):
        freeze_predictions(fwd, data_dir, now=datetime(2026, 10, 26, tzinfo=UTC))

    # The hash isn't committed in the config yet: labels stay closed.
    with pytest.raises(ForwardError, match="no frozen entries"):
        run_labels(fwd, data_dir, LABEL_END)
    fwd = load_forward(write_configs(data_dir.parent, {"ladder": summary.sha256}))
    with pytest.raises(ForwardError, match="in the future"):
        run_labels(fwd, data_dir, datetime(2026, 11, 18, tzinfo=UTC))

    labels = run_labels(fwd, data_dir, LABEL_END)

    assert labels.failed == 0
    assert sorted(set(requested_starts(fake_riot))) == [b[0] for b in fwd.label_buckets]
    assert fake_riot["ids"].call_count == 4 * len(players)  # four weeks, frozen players only
    assert file_hash(base_store_path(data_dir, fwd)) == base_before
    with pytest.raises(ForwardError, match="labels were already collected"):
        run_features(fwd, data_dir, datetime(2026, 11, 20, tzinfo=UTC))

    scored = score_forward(fwd, data_dir, now=datetime(2026, 11, 20, tzinfo=UTC))

    quitters = {p for p in eligible if index(p.split(":")[1]) % 3 == 0}
    assert scored.players == len(eligible)
    assert scored.churned == len(quitters)
    assert set(scored.results) == {"majority", "recency", "logreg", "lightgbm"}
    report = (scored.out_dir / REPORT_FILE).read_text(encoding="utf-8")
    assert "The question set before freezing" in report
    results = json.loads((scored.out_dir / "results.json").read_text(encoding="utf-8"))
    assert results["entries"] == {"ladder": summary.sha256}
    assert not any(p.split(":")[1] in report for p in eligible)  # no identifiers in the report


def test_scoring_refuses_predictions_changed_after_freezing(
    world: tuple[Forward, Path],
) -> None:
    fwd, data_dir = world
    run_features(fwd, data_dir, datetime(2026, 10, 25, tzinfo=UTC))
    summary = freeze_predictions(fwd, data_dir, now=datetime(2026, 10, 25, tzinfo=UTC))
    fwd = load_forward(write_configs(data_dir.parent, {"ladder": summary.sha256}))
    run_labels(fwd, data_dir, LABEL_END)
    entry = entry_path(data_dir, fwd, "ladder")
    entry.write_text(entry.read_text(encoding="utf-8").replace("0.", "0.9", 1), encoding="utf-8")

    with pytest.raises(ForwardError, match="doesn't match the SHA-256"):
        score_forward(fwd, data_dir, now=LABEL_END)


def test_freezing_needs_a_finished_features_collection(world: tuple[Forward, Path]) -> None:
    fwd, data_dir = world

    with pytest.raises(ForwardError, match="lolret forward collect"):
        freeze_predictions(fwd, data_dir, now=datetime(2026, 10, 25, tzinfo=UTC))


def test_freezing_refuses_once_labels_exist(world: tuple[Forward, Path]) -> None:
    fwd, data_dir = world
    run_features(fwd, data_dir, datetime(2026, 10, 25, tzinfo=UTC))
    Store(labels_store_path(data_dir, fwd)).close()

    with pytest.raises(ForwardError, match="must be frozen before"):
        freeze_predictions(fwd, data_dir, now=datetime(2026, 10, 25, tzinfo=UTC))


def test_cli_forward_predict_reports_a_missing_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data" / "raw").mkdir(parents=True)
    Store(tmp_path / "data" / "raw" / "base.sqlite").close()
    path = write_configs(tmp_path)

    result = CliRunner().invoke(app, ["forward", "predict", "-c", str(path)])

    assert result.exit_code == 1


def test_a_freeze_that_fails_midway_can_run_again(
    world: tuple[Forward, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    fwd, data_dir = world
    run_features(fwd, data_dir, datetime(2026, 10, 25, tzinfo=UTC))

    failures = [OSError("disk full")]

    def fails_once() -> str:
        if failures:
            raise failures.pop()
        return "abc1234"

    monkeypatch.setattr("lolret.forward.predict._git_commit", fails_once)
    with pytest.raises(OSError, match="disk full"):
        freeze_predictions(fwd, data_dir, now=datetime(2026, 10, 25, tzinfo=UTC))
    assert not entry_path(data_dir, fwd, "ladder").exists()  # nothing counts as frozen yet

    summary = freeze_predictions(fwd, data_dir, now=datetime(2026, 10, 25, tzinfo=UTC))

    assert summary.sha256 == file_hash(summary.entry)


def test_nets_enter_after_the_ladder_and_are_scored_against_lightgbm(
    world: tuple[Forward, Path],
) -> None:
    fwd, data_dir = world
    write_sequences(sequences_path(data_dir, "base"), examples_path(data_dir, "base"))
    run_features(fwd, data_dir, datetime(2026, 10, 25, tzinfo=UTC))
    with pytest.raises(ForwardError, match="no frozen entries"):  # the ladder comes first
        freeze_nn_entry(fwd, nn_config(), data_dir, now=datetime(2026, 10, 25, tzinfo=UTC))
    ladder = freeze_predictions(fwd, data_dir, now=datetime(2026, 10, 25, tzinfo=UTC))
    fwd = load_forward(write_configs(data_dir.parent, {"ladder": ladder.sha256}))

    nets = freeze_nn_entry(fwd, nn_config(), data_dir, now=datetime(2026, 10, 26, tzinfo=UTC))

    players, preds = read_entry(nets.entry)
    assert set(preds) == {"mlp", "gru", "lightgbm_gru"}
    assert set(players.tolist()) == set(read_entry(ladder.entry)[0].tolist())
    with pytest.raises(ForwardError, match="already frozen"):
        freeze_nn_entry(fwd, nn_config(), data_dir, now=datetime(2026, 10, 26, tzinfo=UTC))

    entries = {"ladder": ladder.sha256, "nn": nets.sha256}
    fwd = load_forward(write_configs(data_dir.parent, entries))
    run_labels(fwd, data_dir, LABEL_END)
    scored = score_forward(fwd, data_dir, now=LABEL_END)

    assert {"lightgbm", "mlp", "gru", "lightgbm_gru"} <= set(scored.results)
    results = json.loads((scored.out_dir / "results.json").read_text(encoding="utf-8"))
    assert set(results["vs_lightgbm"]) == {"mlp", "gru", "lightgbm_gru"}
    assert "Later entries against LightGBM" in (scored.out_dir / REPORT_FILE).read_text(
        encoding="utf-8"
    )
