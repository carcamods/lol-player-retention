"""Contract tests on real (anonymised) Riot responses recorded by the pilot run.

If Riot changes a response shape that later phases rely on, these fail first, with a clear
message, instead of a feature silently turning into NaN.
"""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from lolret.collect.ladder import LeagueEntry

FIXTURES = Path(__file__).parent / "fixtures"
MATCH_ID = re.compile(r"NA1_\d+")

# Fields Phase 3 builds features and labels from.
MATCH_INFO_FIELDS = {
    "gameCreation",
    "gameStartTimestamp",
    "gameEndTimestamp",
    "gameDuration",
    "queueId",
    "gameMode",
    "gameVersion",
    "participants",
}
PARTICIPANT_FIELDS = {
    "puuid",
    "win",
    "kills",
    "deaths",
    "assists",
    "championId",
    "teamPosition",
    "goldEarned",
    "totalMinionsKilled",
    "visionScore",
    "timePlayed",
    "gameEndedInEarlySurrender",
    "gameEndedInSurrender",
    "summonerLevel",
}


def load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_league_entries_parse_and_carry_a_puuid() -> None:
    entries = TypeAdapter(list[LeagueEntry]).validate_python(load("league_entries"))

    assert entries
    assert all(e.puuid.startswith("fixture-puuid-") for e in entries)


def test_match_ids_are_match_ids() -> None:
    ids = load("match_ids")

    assert ids
    assert all(MATCH_ID.fullmatch(i) for i in ids)


def test_match_has_every_field_the_dataset_needs() -> None:
    match = load("match")
    info = match["info"]

    assert info.keys() >= MATCH_INFO_FIELDS
    assert len(info["participants"]) == 10
    for participant in info["participants"]:
        missing = PARTICIPANT_FIELDS - participant.keys()
        assert not missing, f"participant is missing {sorted(missing)}"
    assert info["gameEndTimestamp"] > info["gameStartTimestamp"]


def test_fixtures_hold_no_real_identifiers() -> None:
    text = "".join(
        (FIXTURES / f"{n}.json").read_text(encoding="utf-8")
        for n in ("league_entries", "match_ids", "match")
    )

    # Real PUUIDs are 78-character URL-safe base64 strings.
    assert not re.search(r"[A-Za-z0-9_-]{70,}", text)
    puuids = set(re.findall(r'"puuid": "([^"]+)"', text))
    assert puuids
    assert all(p.startswith("fixture-puuid-") for p in puuids)
