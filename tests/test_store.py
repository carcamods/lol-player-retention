import json
import sqlite3
from pathlib import Path

from lolret.collect.cache import cache_key
from lolret.collect.store import Store, endpoint_name
from lolret.riot.client import RiotResponse


def test_responses_round_trip_including_404(tmp_path: Path) -> None:
    store = Store(tmp_path / "run.sqlite")
    store.put("k200", "match", RiotResponse(200, {"a": [1, 2]}))
    store.put("k404", "match", RiotResponse(404, None))

    assert store.get("k200") == RiotResponse(200, {"a": [1, 2]})
    assert store.get("k404") == RiotResponse(404, None)
    assert store.get("missing") is None


def test_bodies_are_compressed_and_legacy_text_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "run.sqlite"
    store = Store(path)
    body = {"info": {"participants": [{"kills": 3}] * 10}}
    store.put("new", "match", RiotResponse(200, body))
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO responses VALUES ('old', 'match', 200, '{\"a\": 1}', 'then')")
        stored = db.execute("SELECT body FROM responses WHERE key = 'new'").fetchone()[0]

    assert isinstance(stored, bytes)
    assert len(stored) < len(json.dumps(body))
    assert store.get("new") == RiotResponse(200, body)
    assert store.get("old") == RiotResponse(200, {"a": 1})


def test_a_success_clears_an_earlier_failure(tmp_path: Path) -> None:
    store = Store(tmp_path / "run.sqlite")
    store.record_failure("k", "HTTP 503")
    store.record_failure("k", "HTTP 503")
    assert store.summary()["failures"]["open"] == 1

    store.put("k", "match", RiotResponse(200, {}))
    assert store.summary()["failures"]["open"] == 0


def test_players_are_idempotent_and_track_completion(tmp_path: Path) -> None:
    store = Store(tmp_path / "run.sqlite")
    store.add_players("na1", "GOLD", "II", ["p1", "p2"])
    store.add_players("na1", "GOLD", "II", ["p2", "p3"])
    store.mark_complete("na1", "p1")

    assert store.count_players("na1", "GOLD", "II") == 3
    assert [(p.puuid, p.complete) for p in store.players("na1")] == [
        ("p1", True),
        ("p2", False),
        ("p3", False),
    ]
    assert store.summary()["complete"] == {"na1": 1}


def test_read_only_reader_works_while_writer_is_open(tmp_path: Path) -> None:
    path = tmp_path / "run.sqlite"
    writer = Store(path)
    writer.put("k", "match-ids", RiotResponse(200, []))

    reader = Store(path, read_only=True)
    assert reader.summary()["responses"] == {"match-ids": 1}
    reader.close()
    writer.close()


def test_cache_key_is_stable_and_sorted() -> None:
    assert cache_key("na1", "/x", {"b": 2, "a": 1}) == "na1/x?a=1&b=2"
    assert cache_key("americas", "/y", None) == "americas/y"


def test_endpoint_names() -> None:
    assert endpoint_name("/lol/league/v4/entries/RANKED_SOLO_5x5/GOLD/II") == "league-entries"
    assert endpoint_name("/lol/match/v5/matches/by-puuid/P/ids") == "match-ids"
    assert endpoint_name("/lol/match/v5/matches/NA1_1") == "match"
