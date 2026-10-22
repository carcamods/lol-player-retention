from datetime import UTC, datetime, timedelta

import pytest

from lolret.collect.history import bucket_match_ids, recent_before
from lolret.riot.client import Params, RiotEndpoints, RiotResponse

T0 = datetime(2026, 6, 4, tzinfo=UTC)
WEEK = timedelta(days=7)
BUCKETS = [(T0 + WEEK * i, T0 + WEEK * (i + 1)) for i in range(4)]


def test_recent_before_takes_newest_first_and_stops_at_n() -> None:
    ids = [["a2", "a1"], ["b2", "b1"], ["c2", "c1"], ["d1"]]  # each bucket newest first

    assert recent_before(BUCKETS, ids, BUCKETS[3][0], 3) == ["c2", "c1", "b2"]
    assert recent_before(BUCKETS, ids, BUCKETS[3][0], 10) == ["c2", "c1", "b2", "b1", "a2", "a1"]


def test_recent_before_never_looks_past_the_cutoff() -> None:
    ids = [["a1"], ["b1"], ["c1"], ["d1"]]

    assert recent_before(BUCKETS, ids, BUCKETS[1][0], 5) == ["a1"]
    assert recent_before(BUCKETS, ids, BUCKETS[0][0], 5) == []


class PagedIds(RiotEndpoints):
    """Serves 130 match IDs, 100 per page, and records the requests."""

    def __init__(self) -> None:
        self.requests: list[Params] = []

    async def get(self, routing: str, path: str, params: Params | None = None) -> RiotResponse:
        assert params is not None
        self.requests.append(params)
        start = int(params["start"])
        return RiotResponse(200, [f"M{i}" for i in range(start, min(start + 100, 130))])


@pytest.mark.anyio
async def test_bucket_match_ids_paginates_and_uses_a_half_open_window() -> None:
    riot = PagedIds()

    ids = await bucket_match_ids(riot, "americas", "P1", BUCKETS[0])

    assert len(ids) == 130
    assert [r["start"] for r in riot.requests] == [0, 100]
    assert riot.requests[0]["startTime"] == int(BUCKETS[0][0].timestamp())
    assert riot.requests[0]["endTime"] == int(BUCKETS[0][1].timestamp()) - 1
