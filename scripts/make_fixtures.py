"""Build anonymised test fixtures from a collection run's SQLite store.

    uv run python scripts/make_fixtures.py data/raw/pilot.sqlite

Writes tests/fixtures/{league_entries,match_ids,match}.json. Every PUUID, Riot ID, summoner
ID, league ID and match ID is replaced with a fake value, and the script refuses to write if
any original identifier survives. Real IDs would let anyone look the players up.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
NAME_KEYS = {"riotIdGameName", "riotIdName", "summonerName", "gameName"}
TAG_KEYS = {"riotIdTagline", "tagLine"}
OPAQUE_ID_KEYS = {"summonerId", "leagueId"}
MATCH_ID = re.compile(r"[A-Z0-9]+_\d+")


class Anonymiser:
    def __init__(self) -> None:
        self.puuids: dict[str, str] = {}
        self.match_ids: dict[str, str] = {}
        self.originals: set[str] = set()

    def puuid(self, real: str) -> str:
        self.originals.add(real)
        return self.puuids.setdefault(real, f"fixture-puuid-{len(self.puuids) + 1:02d}")

    def match_id(self, real: str) -> str:
        self.originals.add(real)
        return self.match_ids.setdefault(real, f"NA1_{1_000_000_000 + len(self.match_ids) + 1}")

    def walk(self, node: Any, key: str | None = None) -> Any:
        if isinstance(node, dict):
            return {k: self.walk(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [self.walk(v, key) for v in node]
        if key == "gameId":  # numeric, and embedded in other fields such as the match ID
            self.originals.add(str(node))
            return 1_000_000_000
        if not isinstance(node, str):
            return node
        if key in ("puuid", "participants"):
            return self.puuid(node)
        if key == "matchId" or (key is None and MATCH_ID.fullmatch(node)):
            return self.match_id(node)
        if key in NAME_KEYS:
            if len(node) >= 4:  # shorter names would trip the leak check on unrelated text
                self.originals.add(node)
            return "Player"
        if key in TAG_KEYS:
            return "TAG"
        if key in OPAQUE_ID_KEYS:
            self.originals.add(node)
            return "fixture-id"
        return node


def first_body(db: sqlite3.Connection, endpoint: str) -> Any:
    row = db.execute(
        "SELECT body FROM responses WHERE endpoint = ? AND status = 200 AND body NOT IN ('[]')"
        " ORDER BY key LIMIT 1",
        (endpoint,),
    ).fetchone()
    if row is None:
        sys.exit(f"no stored {endpoint} response to build a fixture from")
    return json.loads(row[0])


def main(db_path: Path) -> None:
    db = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    anon = Anonymiser()
    fixtures = {
        "league_entries": anon.walk(first_body(db, "league-entries")[:3]),
        "match_ids": anon.walk(first_body(db, "match-ids")[:5]),
        "match": anon.walk(first_body(db, "match")),
    }
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, data in fixtures.items():
        text = json.dumps(data, indent=1, sort_keys=True)
        leaked = [o for o in anon.originals if o in text]
        if leaked:
            sys.exit(f"refusing to write {name}.json: {len(leaked)} original identifiers remain")
        (FIXTURES / f"{name}.json").write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"wrote tests/fixtures/{name}.json ({len(text) // 1024} KB)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
