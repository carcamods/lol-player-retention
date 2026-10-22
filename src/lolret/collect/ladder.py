"""Sample ranked Solo/Duo players from the ladder.

For each (tier, division): find the last non-empty page (exponential, then binary search),
fetch a few random pages, and draw players at random from them. A seed per division makes the
sample reproducible, and cached pages keep it stable across resumed runs.
"""

import random

from pydantic import BaseModel, ConfigDict, TypeAdapter

from lolret.collect.config import CollectConfig
from lolret.riot.client import RiotEndpoints


class LeagueEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    puuid: str
    tier: str
    rank: str  # Riot's name for the division


_entries = TypeAdapter(list[LeagueEntry])


async def _page(
    riot: RiotEndpoints, platform: str, tier: str, division: str, page: int
) -> list[LeagueEntry]:
    response = await riot.league_entries(platform, tier, division, page)
    if response.status != 200:
        return []
    return _entries.validate_python(response.body)


async def last_page(riot: RiotEndpoints, platform: str, tier: str, division: str) -> int:
    """Number of non-empty pages, in O(log n) requests. 0 if the division is empty."""
    if not await _page(riot, platform, tier, division, 1):
        return 0
    lo, hi = 1, 2  # invariant: page lo has entries, page hi is unknown or empty
    while await _page(riot, platform, tier, division, hi):
        lo, hi = hi, hi * 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if await _page(riot, platform, tier, division, mid):
            lo = mid
        else:
            hi = mid
    return lo


async def sample_division(
    riot: RiotEndpoints, cfg: CollectConfig, platform: str, tier: str, division: str
) -> list[str]:
    """Randomly chosen PUUIDs from one division.

    The pool is shuffled once and the first `players_per_division` are taken, so raising that
    number later keeps every player already sampled and only adds new ones.
    """
    # Sampling, not cryptography: a seeded PRNG is what makes the sample reproducible.
    rng = random.Random(f"{cfg.seed}:{platform}:{tier}:{division}")  # noqa: S311
    pages_total = await last_page(riot, platform, tier, division)
    if pages_total == 0:
        return []
    pages = sorted(rng.sample(range(1, pages_total + 1), min(cfg.pages_per_division, pages_total)))
    pool: dict[str, None] = {}  # insertion-ordered set, so the draw is deterministic
    for page in pages:
        for entry in await _page(riot, platform, tier, division, page):
            pool.setdefault(entry.puuid)
    order = list(pool)
    rng.shuffle(order)
    return order[: cfg.players_per_division]
