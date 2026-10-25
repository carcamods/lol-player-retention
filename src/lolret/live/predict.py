"""Live prediction for one player, with the developer's own key (FR6, ADR 0002).

The cutoff is today 00:00 UTC. The player's match history is fetched and turned into features
by the same code as training: the collector's history helpers, a store, `extract` and
`features.sql`. So a live prediction can't see a feature computed differently from the ones
the model learned on, and the timing rules (ADR 0006) hold. Responses are cached in
`data/raw/live.sqlite`, so asking again the same day costs no request.

Nothing printed or returned identifies the player beyond the Riot ID they were looked up by.
"""

import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path

import duckdb
import numpy as np

from lolret.collect.cache import CachedRiot
from lolret.collect.config import CollectConfig
from lolret.collect.history import bucket_match_ids, recent_before
from lolret.collect.store import Store
from lolret.dataset.build import build_examples
from lolret.dataset.extract import extract
from lolret.forward.collect import LayeredStore
from lolret.model.data import FEATURES, load_examples
from lolret.model.models import Ladder
from lolret.riot.client import RiotClient
from lolret.riot.routing import account_region_for, region_for

DETAILS = 20  # the most recent matches whose details the features read, as in training
LOOKBACK_DAYS = 56
TOP_DRIVERS = 3


class PlayerNotFoundError(LookupError):
    """No account has that Riot ID."""


@dataclass(frozen=True)
class Driver:
    feature: str
    value: float
    contribution: float  # SHAP value in log-odds; positive raises the churn probability


@dataclass(frozen=True)
class LivePrediction:
    riot_id: str
    platform: str
    cutoff: datetime
    eligible: bool  # played in the 28 days before the cutoff (ADR 0006)
    games_28d: int
    days_since_last_game: float | None
    churn: float | None  # calibrated LightGBM probability; None when not eligible
    recency: float | None  # the recency rule's probability, for comparison
    drivers: list[Driver]


def split_riot_id(riot_id: str) -> tuple[str, str]:
    name, sep, tag = riot_id.rpartition("#")
    if not sep or not name or not tag:
        raise ValueError(f"a Riot ID looks like Name#TAG, got {riot_id!r}")
    return name, tag


def live_config(platform: str, cutoff: datetime) -> CollectConfig:
    """A one-cutoff run config: 8 weekly buckets before `cutoff` (and 4 after, never fetched)."""
    start = cutoff.date().toordinal() - LOOKBACK_DAYS
    return CollectConfig.model_validate(
        {
            "run_name": "live",
            "platforms": [platform],
            "tiers": ["GOLD"],  # unused: nobody is sampled
            "divisions": ["I"],
            "players_per_division": 1,
            "pages_per_division": 1,
            "season_start": datetime.fromordinal(start).date(),
            "latest_cutoff": cutoff.date(),
            "n_cutoffs": 1,
            "cutoff_spacing_days": 28,
            "lookback_days": LOOKBACK_DAYS,
            "label_window_days": 28,
            "bucket_days": 7,
            "details_per_cutoff": DETAILS,
            "seed": 0,
        }
    )


def today_cutoff(now: datetime) -> datetime:
    return datetime.combine(now.astimezone(UTC).date(), time(), tzinfo=UTC)


async def fetch_live(
    client: RiotClient, riot_id: str, platform: str, cache: Path, *, now: datetime
) -> tuple[str, datetime]:
    """Fetch what the features need into the cache. Returns the puuid and the cutoff."""
    name, tag = split_riot_id(riot_id)
    cutoff = today_cutoff(now)
    account = await client.account_by_riot_id(account_region_for(platform), name, tag)
    if account.status != 200:
        raise PlayerNotFoundError(f"no account found for {riot_id}")
    puuid: str = account.body["puuid"]
    region = region_for(platform)
    buckets = [b for b in live_config(platform, cutoff).buckets if b[1] <= cutoff]
    store = Store(cache)
    try:
        riot = CachedRiot(client, store)
        ids = [await bucket_match_ids(riot, region, puuid, b) for b in buckets]
        for match_id in recent_before(buckets, ids, cutoff, DETAILS):
            await riot.match(region, match_id)
    finally:
        store.close()
    return puuid, cutoff


def predict_cached(
    puuid: str, riot_id: str, platform: str, cutoff: datetime, ladder: Ladder, cache: Path
) -> LivePrediction:
    """Features from the cache, built exactly as in training, and the ladder's prediction."""
    cfg = live_config(platform, cutoff)
    store = Store(cache, read_only=True)
    with tempfile.TemporaryDirectory() as tmp:
        # A throwaway players table over the cache, so `extract` reads this player only.
        view = LayeredStore(Path(tmp) / "player.sqlite", [store])
        try:
            view.add_players(platform, "UNKNOWN", "", [puuid])
            view.mark_complete(platform, puuid)
            tables = extract(view, cfg, until=cutoff)
        finally:
            view.close()
            store.close()
        path = Path(tmp) / "examples.parquet"
        with duckdb.connect() as con:
            build_examples(con, tables, [cutoff])
            con.table("examples").write_parquet(str(path))
            row = con.execute(
                "SELECT eligible, games_0_7d + games_8_14d + games_15_28d, days_since_last_game "
                "FROM examples"
            ).fetchone()
        examples = load_examples(path, labelled=False)
    if row is None:
        raise RuntimeError("the player's example was not built")
    eligible, games_28d, days = bool(row[0]), int(row[1]), row[2]
    if not eligible:
        return LivePrediction(riot_id, platform, cutoff, False, games_28d, days, None, None, [])

    x = examples.x[:1]
    preds = ladder.predict(x)
    contrib = np.asarray(ladder.lightgbm.booster.predict(x, pred_contrib=True))[0, :-1]
    order = np.argsort(-np.abs(contrib))[:TOP_DRIVERS]
    drivers = [Driver(FEATURES[i], float(x[0, i]), float(contrib[i])) for i in order]
    return LivePrediction(
        riot_id=riot_id,
        platform=platform,
        cutoff=cutoff,
        eligible=True,
        games_28d=games_28d,
        days_since_last_game=None if days is None else float(days),
        churn=float(preds["lightgbm"][0]),
        recency=float(preds["recency"][0]),
        drivers=drivers,
    )


def format_prediction(p: LivePrediction) -> str:
    lines = [f"{p.riot_id} on {p.platform}, as of {p.cutoff:%Y-%m-%d} 00:00 UTC"]
    if p.churn is None or p.recency is None or p.days_since_last_game is None:  # not eligible
        lines += [
            f"{p.games_28d} games in the 28 days before: not covered. The model only predicts for",
            "players who played in the last 4 weeks (docs/decisions/0006-eligible-population.md).",
        ]
        return "\n".join(lines)
    lines += [
        f"{p.games_28d} games in the last 28 days; the last one ended "
        f"{p.days_since_last_game:.1f} days before.",
        f"Chance of playing no game in the next 28 days: {p.churn:.0%} "
        f"(LightGBM; the recency rule alone says {p.recency:.0%}).",
        "Biggest drivers:",
    ]
    for d in p.drivers:
        effect = "raises" if d.contribution > 0 else "lowers"
        lines.append(f"  {d.feature} = {d.value:g}: {effect} it ({d.contribution:+.2f} log-odds)")
    return "\n".join(lines)
