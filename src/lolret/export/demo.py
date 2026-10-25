"""A made-up snapshot with the real one's structure, so CI can build the site without data.

`python -m lolret.export.demo site/data/snapshot.json`. Every value is random; nothing comes
from a real player. `tests/test_export.py` checks that its structure matches a real export's,
so the site can't pass CI on a demo that has drifted from what `lolret export` writes.
"""

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

from lolret.export.snapshot import REGIONS, WEEKS_AFTER, WEEKS_BEFORE
from lolret.model.data import FEATURES

MODELS = ("majority", "recency", "logreg", "lightgbm", "mlp", "gru", "lightgbm_gru")
TIERS = ("IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND")


def _metric(rng: np.random.Generator) -> dict[str, Any]:
    pr, roc, brier = rng.uniform(0.2, 0.5), rng.uniform(0.5, 0.85), rng.uniform(0.1, 0.15)
    return {
        "pr_auc": pr,
        "pr_auc_ci": [pr - 0.06, pr + 0.07],
        "roc_auc": roc,
        "roc_auc_ci": [roc - 0.03, roc + 0.03],
        "brier": brier,
        "brier_ci": [brier - 0.01, brier + 0.01],
    }


def _group(rng: np.random.Generator) -> dict[str, Any]:
    n = int(rng.integers(100, 400))
    scores = {"pr_auc": rng.uniform(0.3, 0.6), "roc_auc": rng.uniform(0.75, 0.9)}
    return {
        "examples": n,
        "churned": int(n * rng.uniform(0.05, 0.25)),
        "recency": scores | {"brier": 0.12, "log_loss": 0.38},
        "lightgbm": scores | {"brier": 0.12, "log_loss": 0.37},
    }


def demo_snapshot(players: int = 200, seed: int = 0) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(1, players + 1):
        churn = float(rng.beta(1.5, 6))
        rows.append(
            {
                "id": f"Player {i:04d}",
                "region": str(rng.choice(list(REGIONS.values()))),
                "tier": str(rng.choice(TIERS)),
                "division": str(rng.choice(["I", "II", "III", "IV"])),
                "churn": round(churn, 4),
                "recency": round(float(np.clip(churn + rng.normal(0, 0.05), 0.01, 0.99)), 4),
                "churned": bool(rng.random() < churn),
                "games_28d": int(rng.integers(1, 80)),
                "days_since_last_game": round(float(rng.exponential(5)), 3),
                "win_rate": round(float(rng.uniform(0.3, 0.7)), 3),
                "drivers": [
                    {
                        "feature": str(f),
                        "value": round(float(rng.uniform(0, 20)), 3),
                        "effect": round(float(rng.normal(0, 0.5)), 3),
                    }
                    for f in rng.choice(FEATURES, size=3, replace=False)
                ],
                "weeks": [int(g) for g in rng.integers(0, 15, WEEKS_BEFORE + WEEKS_AFTER)],
            }
        )
    vs = {"pr_auc_diff": 0.01, "pr_auc_diff_ci": [-0.03, 0.05]}
    return {
        "meta": {
            "dataset": "demo",
            "cutoff": "2026-09-24",
            "exported": "2026-10-25T00:00:00+00:00",
            "model": "Demo data: random numbers, not a model",
            "players": players,
            "churn_rate": round(float(np.mean([r["churned"] for r in rows])), 4),
            "weeks": {"before": WEEKS_BEFORE, "after": WEEKS_AFTER},
            "note": "Demo snapshot for building the site in CI; every value is random.",
        },
        "metrics": {name: _metric(rng) for name in MODELS},
        "vs_recency": {name: vs for name in MODELS if name not in ("majority", "recency")},
        "train": {"examples": 5000, "players": 3000, "churn_rate": 0.18},
        "by_group": {
            "region": {platform: _group(rng) for platform in REGIONS},
            "tier": {tier: _group(rng) for tier in TIERS},
        },
        "forward": {
            "cutoff": "2026-10-22",
            "outcomes_until": "2026-11-19",
            "entries": {"ladder": "0" * 64},
            "status": "pending",
            "frozen_at": "2026-10-25",
            "players": 3000,
        },
        "players": rows,
    }


def main(argv: list[str]) -> None:
    path = Path(argv[1] if len(argv) > 1 else "site/data/snapshot.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(demo_snapshot(), indent=1) + "\n", encoding="utf-8")
    print(f"Wrote a demo snapshot (random values) to {path}")


if __name__ == "__main__":
    main(sys.argv)
