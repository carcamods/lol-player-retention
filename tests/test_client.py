import httpx
import pytest
import respx

from lolret.riot.client import RiotAuthError, RiotClient, RiotRequestError, RiotResponse

AMERICAS = "https://americas.api.riotgames.com"
MATCH_PATH = "/lol/match/v5/matches/NA1_1"


class Sleeps:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_client(http: httpx.AsyncClient, sleeps: Sleeps, max_attempts: int = 5) -> RiotClient:
    return RiotClient(
        "test-key", limits=[(10_000, 1.0)], http=http, max_attempts=max_attempts, sleep=sleeps
    )


@pytest.mark.anyio
async def test_key_is_sent_in_header_never_in_url() -> None:
    with respx.mock(base_url=AMERICAS) as router:
        route = router.get(MATCH_PATH).respond(200, json={"ok": True})
        async with httpx.AsyncClient() as http:
            response = await make_client(http, Sleeps()).match("americas", "NA1_1")

    assert response == RiotResponse(200, {"ok": True})
    request = route.calls.last.request
    assert request.headers["X-Riot-Token"] == "test-key"
    assert "test-key" not in str(request.url)


@pytest.mark.anyio
async def test_match_ids_sends_time_window_params() -> None:
    with respx.mock(base_url=AMERICAS) as router:
        route = router.get("/lol/match/v5/matches/by-puuid/P1/ids").respond(200, json=["NA1_9"])
        async with httpx.AsyncClient() as http:
            client = make_client(http, Sleeps())
            response = await client.match_ids("americas", "P1", start_time=10, end_time=20)

    assert response.body == ["NA1_9"]
    params = route.calls.last.request.url.params
    assert dict(params) == {"startTime": "10", "endTime": "20", "start": "0", "count": "100"}


@pytest.mark.anyio
async def test_404_is_returned_not_raised() -> None:
    with respx.mock(base_url=AMERICAS) as router:
        router.get(MATCH_PATH).respond(404)
        async with httpx.AsyncClient() as http:
            response = await make_client(http, Sleeps()).match("americas", "NA1_1")

    assert response == RiotResponse(404, None)


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_key_raises_without_retrying(status: int) -> None:
    with respx.mock(base_url=AMERICAS) as router:
        route = router.get(MATCH_PATH).respond(status)
        async with httpx.AsyncClient() as http:
            with pytest.raises(RiotAuthError, match="RIOT_API_KEY"):
                await make_client(http, Sleeps()).match("americas", "NA1_1")

    assert route.call_count == 1


@pytest.mark.anyio
async def test_429_waits_for_retry_after_then_succeeds() -> None:
    sleeps = Sleeps()
    with respx.mock(base_url=AMERICAS) as router:
        router.get(MATCH_PATH).mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "7"}),
                httpx.Response(200, json={}),
            ]
        )
        async with httpx.AsyncClient() as http:
            response = await make_client(http, sleeps).match("americas", "NA1_1")

    assert response.status == 200
    assert sleeps.calls == [7.0]


@pytest.mark.anyio
async def test_server_errors_back_off_then_raise() -> None:
    sleeps = Sleeps()
    with respx.mock(base_url=AMERICAS) as router:
        route = router.get(MATCH_PATH).respond(503)
        async with httpx.AsyncClient() as http:
            with pytest.raises(RiotRequestError, match="after 3 attempts"):
                await make_client(http, sleeps, max_attempts=3).match("americas", "NA1_1")

    assert route.call_count == 3
    assert sleeps.calls == [1.0, 2.0]


@pytest.mark.anyio
async def test_network_errors_are_retried() -> None:
    with respx.mock(base_url=AMERICAS) as router:
        router.get(MATCH_PATH).mock(
            side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={})]
        )
        async with httpx.AsyncClient() as http:
            response = await make_client(http, Sleeps()).match("americas", "NA1_1")

    assert response.status == 200
