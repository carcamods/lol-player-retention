"""SQLite store for a collection run: cached API responses, failures and sampled players.

SQLite (WAL mode) rather than DuckDB because a run is a long, write-heavy job: every response
is committed as it arrives, so an interrupted run loses nothing, and `lolret status` can read
the file while `lolret collect` is writing to it. Phase 3 reads this file for analysis.

Bodies are stored as zlib-compressed JSON: a match is ~80 KB raw but ~11 KB compressed, which
keeps a full run at ~2 GB instead of ~13 GB.
"""

import json
import sqlite3
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lolret.riot.client import RiotResponse

SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key        TEXT PRIMARY KEY,   -- routing + path + sorted query string
    endpoint   TEXT NOT NULL,      -- league-entries | match-ids | match
    status     INTEGER NOT NULL,   -- 200 or 404
    body       BLOB,               -- zlib-compressed JSON; NULL for 404
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS failures (
    key      TEXT PRIMARY KEY,
    error    TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    last_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS players (
    platform    TEXT NOT NULL,
    puuid       TEXT NOT NULL,
    tier        TEXT NOT NULL,
    division    TEXT NOT NULL,
    sampled_at  TEXT NOT NULL,
    complete_at TEXT,              -- set once every request for this player succeeded
    PRIMARY KEY (platform, puuid)
);
"""


def endpoint_name(path: str) -> str:
    if path.startswith("/lol/league/v4/entries/"):
        return "league-entries"
    if path.endswith("/ids"):
        return "match-ids"
    if path.startswith("/lol/match/v5/matches/"):
        return "match"
    return "other"


@dataclass(frozen=True)
class Player:
    platform: str
    puuid: str
    tier: str
    division: str
    complete: bool


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def encode_body(body: Any) -> bytes:
    return zlib.compress(json.dumps(body, separators=(",", ":")).encode("utf-8"))


def decode_body(stored: bytes | str) -> Any:
    """Decode a stored body. Plain-text JSON from runs made before compression still loads."""
    if isinstance(stored, bytes):
        return json.loads(zlib.decompress(stored))
    return json.loads(stored)


class Store:
    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        if read_only:
            # Lets `lolret status` read while `lolret collect` is writing.
            self._db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    # Responses -------------------------------------------------------------

    def get(self, key: str) -> RiotResponse | None:
        row = self._db.execute(
            "SELECT status, body FROM responses WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        status, body = row
        return RiotResponse(status, None if body is None else decode_body(body))

    def put(self, key: str, endpoint: str, response: RiotResponse) -> None:
        body = None if response.body is None else encode_body(response.body)
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?)",
                (key, endpoint, response.status, body, _now()),
            )
            self._db.execute("DELETE FROM failures WHERE key = ?", (key,))

    def record_failure(self, key: str, error: str) -> None:
        with self._db:
            self._db.execute(
                """INSERT INTO failures VALUES (?, ?, 1, ?)
                   ON CONFLICT(key) DO UPDATE SET
                     error = excluded.error, attempts = attempts + 1, last_at = excluded.last_at""",
                (key, error, _now()),
            )

    # Players ---------------------------------------------------------------

    def add_players(self, platform: str, tier: str, division: str, puuids: Iterable[str]) -> None:
        now = _now()
        with self._db:
            self._db.executemany(
                "INSERT OR IGNORE INTO players VALUES (?, ?, ?, ?, ?, NULL)",
                [(platform, p, tier, division, now) for p in puuids],
            )

    def count_players(self, platform: str, tier: str, division: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) FROM players WHERE platform = ? AND tier = ? AND division = ?",
            (platform, tier, division),
        ).fetchone()
        return int(row[0])

    def players(self, platform: str) -> list[Player]:
        rows = self._db.execute(
            """SELECT platform, puuid, tier, division, complete_at IS NOT NULL FROM players
               WHERE platform = ? ORDER BY tier, division, puuid""",
            (platform,),
        ).fetchall()
        return [Player(r[0], r[1], r[2], r[3], bool(r[4])) for r in rows]

    def mark_complete(self, platform: str, puuid: str) -> None:
        with self._db:
            self._db.execute(
                "UPDATE players SET complete_at = ? WHERE platform = ? AND puuid = ?",
                (_now(), platform, puuid),
            )

    # Reporting -------------------------------------------------------------

    def summary(self) -> dict[str, dict[str, int]]:
        responses = dict(
            self._db.execute("SELECT endpoint, COUNT(*) FROM responses GROUP BY endpoint")
        )
        players = {
            platform: total
            for platform, total in self._db.execute(
                "SELECT platform, COUNT(*) FROM players GROUP BY platform"
            )
        }
        complete = {
            platform: done
            for platform, done in self._db.execute(
                "SELECT platform, COUNT(*) FROM players WHERE complete_at IS NOT NULL "
                "GROUP BY platform"
            )
        }
        failures = self._db.execute("SELECT COUNT(*) FROM failures").fetchone()[0]
        return {
            "responses": responses,
            "players": players,
            "complete": complete,
            "failures": {"open": int(failures)},
        }
