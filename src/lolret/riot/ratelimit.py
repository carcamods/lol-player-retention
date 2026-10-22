"""Client-side rate limiting.

Riot enforces several windows at once for each routing value, for example
"20 requests per 1 s and 100 per 120 s". `RateLimiter` keeps a log of recent request times
for each window and waits until every window has room. A sliding log is at least as strict as
Riot's fixed windows, so staying under it never triggers a 429.
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable

Window = tuple[int, float]  # (max requests, period in seconds)


def parse_limits(spec: str) -> list[Window]:
    """Parse Riot's limit format, e.g. "20:1,100:120" -> [(20, 1.0), (100, 120.0)]."""
    windows: list[Window] = []
    for part in spec.split(","):
        count, period = part.strip().split(":")
        windows.append((int(count), float(period)))
    return windows


class RateLimiter:
    def __init__(
        self,
        windows: list[Window],
        *,
        margin: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._windows = windows
        self._logs: list[deque[float]] = [deque() for _ in windows]
        # Extra seconds added to every period, to absorb clock and network jitter.
        self._margin = margin
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request is allowed in every window, then record it."""
        async with self._lock:
            while True:
                now = self._clock()
                wait = 0.0
                for (limit, period), log in zip(self._windows, self._logs, strict=True):
                    span = period + self._margin
                    while log and now - log[0] >= span:
                        log.popleft()
                    if len(log) >= limit:
                        wait = max(wait, log[0] + span - now)
                if wait <= 0:
                    for log in self._logs:
                        log.append(now)
                    return
                await self._sleep(wait)
