import pytest

from lolret.riot.ratelimit import RateLimiter, parse_limits


class FakeClock:
    """A clock that only moves when the limiter sleeps, so tests run instantly."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_parse_limits() -> None:
    assert parse_limits("20:1,100:120") == [(20, 1.0), (100, 120.0)]
    assert parse_limits(" 500:10 ") == [(500, 10.0)]


@pytest.mark.anyio
async def test_waits_until_every_window_has_room() -> None:
    clock = FakeClock()
    limiter = RateLimiter([(2, 1.0), (3, 10.0)], margin=0.0, clock=clock, sleep=clock.sleep)

    times = []
    for _ in range(4):
        await limiter.acquire()
        times.append(clock.now)

    # Two at once; the third waits for the 1 s window; the fourth waits for the 10 s window.
    assert times == [0.0, 0.0, 1.0, 10.0]


@pytest.mark.anyio
async def test_margin_is_added_to_every_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter([(1, 1.0)], margin=0.25, clock=clock, sleep=clock.sleep)

    await limiter.acquire()
    await limiter.acquire()

    assert clock.now == pytest.approx(1.25)
