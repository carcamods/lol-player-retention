"""Dataset tests: feature values, the leak guard, extraction from a store, and the build output."""

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pytest

from lolret.collect.cache import cache_key
from lolret.collect.config import CollectConfig
from lolret.collect.store import Store
from lolret.dataset.build import build_dataset, build_examples
from lolret.dataset.extract import (
    BUCKETS_SCHEMA,
    MATCHES_SCHEMA,
    PLAYERS_SCHEMA,
    Tables,
    extract,
    participant_row,
)
from lolret.riot.client import RiotResponse

T = datetime(2026, 9, 24)  # naive UTC, like the tables
WEEK = timedelta(days=7)
LABEL = "churned"
FIXTURE_MATCH = Path(__file__).parent / "fixtures" / "match.json"

Row = dict[str, Any]


def player(puuid: str) -> Row:
    return {"platform": "na1", "puuid": puuid, "tier": "GOLD", "division": "II"}


def weeks(puuid: str, games: dict[int, int], first: int = -8, last: int = 3) -> list[Row]:
    """Weekly buckets relative to T: week k covers [T + k weeks, T + k+1 weeks)."""
    return [
        {
            "platform": "na1",
            "puuid": puuid,
            "bucket_start": T + k * WEEK,
            "bucket_end": T + (k + 1) * WEEK,
            "games": games.get(k, 0),
        }
        for k in range(first, last + 1)
    ]


def game(puuid: str, i: int, end: datetime, *, win: bool, **overrides: Any) -> Row:
    minutes = overrides.pop("minutes", 30)
    row = {
        "platform": "na1",
        "puuid": puuid,
        "match_id": f"NA1_{puuid}_{i}",
        "game_start": end - timedelta(minutes=minutes),
        "game_end": end,
        "queue_id": 420,
        "duration_s": minutes * 60,
        "win": win,
        "kills": 5,
        "deaths": 5,
        "assists": 5,
        "champion_id": 1,
        "team_position": "TOP",
        "remake": False,
        "surrendered": False,
    }
    return row | overrides


def built(
    players: list[Row],
    buckets: list[Row],
    matches: list[Row],
    cutoffs: list[datetime],
    table: str = "examples",
) -> list[Row]:
    tables = Tables(
        pa.Table.from_pylist(players, PLAYERS_SCHEMA),
        pa.Table.from_pylist(buckets, BUCKETS_SCHEMA),
        pa.Table.from_pylist(matches, MATCHES_SCHEMA),
    )
    con = duckdb.connect()
    build_examples(con, tables, cutoffs)
    cursor = con.execute(f"SELECT * FROM {table}")  # noqa: S608 (a test-chosen table name)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def examples(
    players: list[Row], buckets: list[Row], matches: list[Row], cutoffs: list[datetime]
) -> list[Row]:
    return built(players, buckets, matches, cutoffs)


def sequences(
    players: list[Row], buckets: list[Row], matches: list[Row], cutoffs: list[datetime]
) -> list[Row]:
    return built(players, buckets, matches, cutoffs, table="sequences")


def test_features_and_label_for_a_hand_built_player() -> None:
    h = timedelta(hours=1)
    matches = [
        game("A", 1, T - 2 * h, win=False, kills=2, deaths=4, assists=2),
        game("A", 2, T - 3 * h, win=False, champion_id=2),
        game("A", 3, T - 24 * h, win=True, champion_id=3, team_position="JUNGLE"),
        game("A", 4, T - 48 * h, win=True, queue_id=450, team_position=None),
        # Still running at T: its result is unknown at T, so it must not count.
        game("A", 5, T + 20 * timedelta(minutes=1), win=False, minutes=30),
        # After T: must not count either.
        game("A", 6, T + 72 * h, win=True),
    ]
    buckets = weeks("A", {-1: 3, -2: 2, -3: 1, -4: 1, -6: 4})  # nothing after T

    [a] = examples([player("A")], buckets, matches, [T])

    assert (a["eligible"], a[LABEL]) == (True, True)
    assert (a["games_0_7d"], a["games_8_14d"], a["games_15_28d"], a["games_29_56d"]) == (3, 2, 2, 4)
    assert a["active_weeks_8w"] == 5
    assert a["recent_games"] == 4
    assert a["days_since_last_game"] == pytest.approx(2 / 24)
    assert a["win_rate"] == pytest.approx(0.5)
    assert a["loss_streak"] == 2
    assert a["kda"] == pytest.approx((1 + 2 + 2 + 2) / 4)
    assert a["ranked_share"] == pytest.approx(0.75)
    assert a["aram_share"] == pytest.approx(0.25)
    assert a["champion_diversity"] == pytest.approx(0.75)
    assert a["main_role_share"] == pytest.approx(2 / 3)
    # Games 1 and 2 are 30 minutes apart; game 3 ended 20.5 h before game 2 started.
    assert a["last_session_games"] == 2


def test_sequence_for_a_hand_built_player() -> None:
    h = timedelta(hours=1)
    matches = [
        game("A", 1, T - 2 * h, win=False, kills=2, deaths=4, assists=2),
        game("A", 2, T - 3 * h, win=False, champion_id=2),
        game("A", 3, T - 24 * h, win=True, champion_id=2, team_position="JUNGLE"),
        game("A", 4, T + 20 * timedelta(minutes=1), win=False),  # still running at T
    ]

    rows = sequences([player("A")], weeks("A", {-1: 4}), matches, [T])

    assert [r["rn"] for r in rows] == [1, 2, 3]
    assert [r["hours_before_cutoff"] for r in rows] == pytest.approx([2, 3, 24])
    # Game 1 started 30 minutes after game 2 ended; game 2 started 20.5 h after game 3 ended.
    assert [r["gap_hours"] for r in rows[:2]] == pytest.approx([0.5, 20.5])
    assert rows[2]["gap_hours"] is None  # the oldest game in view
    assert [r["same_champion"] for r in rows] == [False, True, None]
    assert (rows[0]["win"], rows[0]["kills"], rows[2]["team_position"]) == (False, 2, "JUNGLE")


def test_a_player_with_no_games_is_ineligible_with_empty_features() -> None:
    [b] = examples([player("B")], weeks("B", {}), [], [T])

    assert (b["eligible"], b[LABEL], b["recent_games"]) == (False, True, 0)
    assert b["days_since_last_game"] is None


def test_playing_after_the_cutoff_means_not_churned() -> None:
    [c] = examples([player("C")], weeks("C", {-1: 1, 2: 1}), [], [T])

    assert c[LABEL] is False


def test_label_is_unknown_when_the_window_is_not_fully_observed() -> None:
    [d] = examples([player("D")], weeks("D", {-1: 1}, last=1), [], [T])  # only 2 weeks after T

    assert d[LABEL] is None


def random_world(seed: int) -> tuple[list[Row], list[Row], list[Row]]:
    rng = random.Random(seed)
    players, buckets, matches = [], [], []
    for p in range(6):
        puuid = f"P{p}"
        players.append(player(puuid))
        buckets += weeks(puuid, {k: rng.randint(0, 6) for k in range(-12, 4)}, first=-12)
        for i in range(rng.randint(0, 60)):
            end = T - 12 * WEEK + timedelta(minutes=rng.randint(0, 16 * 7 * 24 * 60))
            matches.append(
                game(
                    puuid,
                    i,
                    end,
                    win=rng.random() < 0.5,
                    minutes=rng.randint(4, 45),
                    deaths=rng.randint(0, 12),
                    champion_id=rng.randint(1, 8),
                    queue_id=rng.choice([420, 440, 450, 400]),
                    team_position=rng.choice(["TOP", "MIDDLE", None]),
                )
            )
    return players, buckets, matches


def same(left: Any, right: Any) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return left == pytest.approx(right)
    return bool(left == right)


@pytest.mark.parametrize("seed", range(5))
def test_leak_guard_features_only_see_data_before_the_cutoff(seed: int) -> None:
    """Deleting everything after the cutoff must not change a single feature."""
    players, buckets, matches = random_world(seed)
    cutoffs = [T - 8 * WEEK, T - 4 * WEEK, T]

    for cutoff in cutoffs:
        full = examples(players, buckets, matches, [cutoff])
        truncated = examples(
            players,
            [b for b in buckets if b["bucket_end"] <= cutoff],
            [m for m in matches if m["game_end"] <= cutoff],
            [cutoff],
        )
        assert len(full) == len(truncated) == len(players)
        for row_full, row_truncated in zip(full, truncated, strict=True):
            for column, value in row_full.items():
                if column == LABEL:
                    continue
                assert same(value, row_truncated[column]), (cutoff, row_full["puuid"], column)


@pytest.mark.parametrize("seed", range(5))
def test_leak_guard_sequences_only_see_data_before_the_cutoff(seed: int) -> None:
    """The same guard for the neural nets' match sequences."""
    players, buckets, matches = random_world(seed)

    for cutoff in [T - 8 * WEEK, T - 4 * WEEK, T]:
        full = sequences(players, buckets, matches, [cutoff])
        truncated = sequences(
            players,
            [b for b in buckets if b["bucket_end"] <= cutoff],
            [m for m in matches if m["game_end"] <= cutoff],
            [cutoff],
        )
        assert len(full) == len(truncated)
        for row_full, row_truncated in zip(full, truncated, strict=True):
            for column, value in row_full.items():
                assert same(value, row_truncated[column]), (cutoff, row_full["puuid"], column)


def test_participant_row_from_a_real_match() -> None:
    match = json.loads(FIXTURE_MATCH.read_text(encoding="utf-8"))
    someone = match["info"]["participants"][0]

    row = participant_row("na1", someone["puuid"], match)

    assert row is not None
    assert row["match_id"] == match["metadata"]["matchId"]
    assert row["game_end"] > row["game_start"]
    assert row["win"] is bool(someone["win"])
    assert participant_row("na1", "not-in-this-match", match) is None


def one_week_config(cutoff: datetime) -> CollectConfig:
    return CollectConfig.model_validate(
        {
            "run_name": "t",
            "platforms": ["na1"],
            "tiers": ["GOLD"],
            "divisions": ["II"],
            "players_per_division": 1,
            "pages_per_division": 1,
            "season_start": "2026-01-01",
            "latest_cutoff": cutoff.date().isoformat(),
            "n_cutoffs": 1,
            "cutoff_spacing_days": 7,
            "lookback_days": 7,
            "label_window_days": 28,
            "bucket_days": 7,
            "details_per_cutoff": 20,
            "seed": 1,
        }
    )


def fill_store(store: Store, cfg: CollectConfig, puuid: str, match: dict[str, Any]) -> None:
    """Store what a collection run would have stored: one match in the week before the cutoff."""
    store.add_players("na1", "GOLD", "II", [puuid])
    for i, (start, end) in enumerate(cfg.buckets):
        params = {
            "startTime": int(start.timestamp()),
            "endTime": int(end.timestamp()) - 1,
            "start": 0,
            "count": 100,
        }
        ids = [match["metadata"]["matchId"]] if i == 0 else []
        key = cache_key("americas", f"/lol/match/v5/matches/by-puuid/{puuid}/ids", params)
        store.put(key, "match-ids", RiotResponse(200, ids))
    match_key = cache_key("americas", f"/lol/match/v5/matches/{match['metadata']['matchId']}", None)
    store.put(match_key, "match", RiotResponse(200, match))
    store.mark_complete("na1", puuid)


def test_extract_and_build_from_a_store(tmp_path: Path) -> None:
    match = json.loads(FIXTURE_MATCH.read_text(encoding="utf-8"))
    puuid = match["info"]["participants"][0]["puuid"]
    game_end = datetime.fromtimestamp(match["info"]["gameEndTimestamp"] / 1000, UTC)
    cutoff = (game_end + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    cfg = one_week_config(cutoff)
    store = Store(tmp_path / "run.sqlite")
    fill_store(store, cfg, puuid, match)
    store.add_players("na1", "GOLD", "II", ["unfinished"])  # not complete: must be skipped

    tables = extract(store, cfg)

    assert tables.players.column("puuid").to_pylist() == [puuid]
    assert tables.buckets.column("games").to_pylist() == [1, 0, 0, 0, 0]
    assert tables.matches.num_rows == 1

    summary = build_dataset(cfg, store, tmp_path / "out")

    assert (summary.players, summary.examples, summary.eligible) == (1, 1, 1)
    assert summary.churn_rate_eligible == 1.0
    assert (tmp_path / "out" / "examples.parquet").exists()
    assert summary.path.exists()
