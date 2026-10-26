from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

import pytest
from conftest import REPO_ROOT
from pydantic import ValidationError

from lolret.collect.config import CollectConfig, load_config


def utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def base_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "run_name": "test",
        "platforms": ["na1"],
        "tiers": ["GOLD"],
        "divisions": ["II"],
        "players_per_division": 3,
        "pages_per_division": 2,
        "season_start": "2026-01-08",
        "latest_cutoff": "2026-09-24",
        "n_cutoffs": 3,
        "cutoff_spacing_days": 28,
        "lookback_days": 56,
        "label_window_days": 28,
        "bucket_days": 7,
        "details_per_cutoff": 20,
        "seed": 42,
    }
    return config | overrides


@pytest.mark.parametrize("name", ["collect.yaml", "collect-pilot.yaml", "collect-bronze.yaml"])
def test_shipped_configs_are_valid(name: str) -> None:
    cfg = load_config(REPO_ROOT / "configs" / name)

    assert cfg.cutoffs == [utc(2026, 7, 30), utc(2026, 8, 27), utc(2026, 9, 24)]


def test_buckets_tile_the_range_and_align_with_cutoffs() -> None:
    cfg = CollectConfig.model_validate(base_config())
    buckets = cfg.buckets

    assert buckets[0][0] == cfg.range_start == utc(2026, 6, 4)
    assert buckets[-1][1] == cfg.range_end == utc(2026, 10, 22)
    assert len(buckets) == 20  # 140 days / 7
    assert all(a[1] == b[0] for a, b in pairwise(buckets))
    boundaries = {start for start, _ in buckets}
    assert all(cutoff in boundaries for cutoff in cfg.cutoffs)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"lookback_days": 50}, "multiple of bucket_days"),
        ({"cutoff_spacing_days": 10}, "multiple of bucket_days"),
        ({"season_start": "2026-07-01"}, "before the season start"),
        ({"platforms": ["na1", "xx9"]}, "unknown platforms"),
        ({"tiers": ["MASTER"]}, "tiers"),
        ({"surprise": 1}, "surprise"),
        ({"base_run": "test"}, "can't read from itself"),
    ],
)
def test_invalid_configs_are_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        CollectConfig.model_validate(base_config(**overrides))


def test_label_windows_must_be_in_the_past() -> None:
    cfg = CollectConfig.model_validate(base_config())

    cfg.require_complete_label_windows(utc(2026, 10, 22))
    with pytest.raises(ValueError, match="in the future"):
        cfg.require_complete_label_windows(utc(2026, 10, 22) - timedelta(seconds=1))
