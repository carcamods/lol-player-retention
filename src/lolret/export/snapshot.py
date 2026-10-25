"""Export the anonymised snapshot the public site reads (FR4, ADR 0002, ADR 0014).

Players: the held-out test players at the latest cutoff, whom the model never saw. Each gets
the LightGBM probability, the recency rule's, what actually happened, the three biggest SHAP
drivers, and weekly game counts from 8 weeks before the cutoff to 4 weeks after.

Identifiers: players are numbered "Player 0001", "Player 0002"... in the order of a salted
SHA-256 of their PUUID. The salt is random for every export and never stored, so a number
can't be traced back to an account, and two exports number players differently. No PUUID,
Riot ID or match ID is written. The file goes to `data/snapshot/<dataset>/` and stays there
until the owner decides to publish it.
"""

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from lolret.model.config import TrainConfig
from lolret.model.data import FEATURES, load_examples, split_by_player_and_time
from lolret.model.models import Ladder
from lolret.model.train import METRICS_FILE, examples_path, models_dir

SNAPSHOT_FILE = "snapshot.json"
TOP_DRIVERS = 3
WEEKS_BEFORE, WEEKS_AFTER = 8, 4
REGIONS = {"na1": "NA", "euw1": "EUW", "kr": "KR"}
SHOWN = ("majority", "recency", "logreg", "lightgbm", "mlp", "gru", "lightgbm_gru")


def snapshot_path(data_dir: Path, dataset: str) -> Path:
    return data_dir / "snapshot" / dataset / SNAPSHOT_FILE


def anonymous_ids(players: list[str], salt: bytes) -> dict[str, str]:
    """ "Player 0001"... in the order of a salted hash: random, and untraceable without the salt."""
    order = sorted(players, key=lambda p: hashlib.sha256(salt + p.encode()).hexdigest())
    return {player: f"Player {i:04d}" for i, player in enumerate(order, start=1)}


def _weeks(data_dir: Path, dataset: str, cutoff: datetime) -> dict[str, list[int]]:
    """Games per week from 8 weeks before the cutoff to 4 after, per "platform:puuid"."""
    start = cutoff - timedelta(weeks=WEEKS_BEFORE)
    db = data_dir / "processed" / dataset / "dataset.duckdb"
    with duckdb.connect(str(db), read_only=True) as con:
        rows = con.execute(
            "SELECT platform || ':' || puuid, bucket_start, games FROM buckets "
            "WHERE bucket_start >= ? AND bucket_end <= ? ORDER BY 1, 2",
            [start, cutoff + timedelta(weeks=WEEKS_AFTER)],
        ).fetchall()
    weeks: dict[str, list[int]] = {}
    for player, bucket_start, games in rows:
        counts = weeks.setdefault(player, [0] * (WEEKS_BEFORE + WEEKS_AFTER))
        counts[(bucket_start - start).days // 7] = int(games)
    return weeks


@dataclass(frozen=True)
class ExportSummary:
    path: Path
    players: int
    churned: int


def export_snapshot(
    cfg: TrainConfig, data_dir: Path, *, now: datetime, salt: bytes | None = None
) -> ExportSummary:
    model_dir = models_dir(data_dir, cfg.dataset)
    if not (model_dir / METRICS_FILE).exists():
        raise FileNotFoundError(f"no trained models in {model_dir}: run `lolret train` first")
    metrics = json.loads((model_dir / METRICS_FILE).read_text(encoding="utf-8"))
    source = examples_path(data_dir, cfg.dataset)
    _, test = split_by_player_and_time(load_examples(source), cfg.test_fraction, cfg.seed)
    cutoff = test.cutoff.max().item()

    with duckdb.connect() as con:
        meta = {
            f"{platform}:{puuid}": (tier, division)
            for platform, puuid, tier, division in con.execute(
                "SELECT platform, puuid, tier, division FROM read_parquet(?) WHERE cutoff = ?",
                [str(source), cutoff],
            ).fetchall()
        }
    ladder = Ladder.load(model_dir)
    preds = ladder.predict(test.x)
    contrib = np.asarray(ladder.lightgbm.booster.predict(test.x, pred_contrib=True))[:, :-1]
    weeks = _weeks(data_dir, cfg.dataset, cutoff)
    ids = anonymous_ids(test.player.tolist(), salt or secrets.token_bytes(16))

    def value(row: int, name: str) -> float | None:
        v = float(test.x[row, FEATURES.index(name)])
        return None if np.isnan(v) else round(v, 3)

    players: list[dict[str, Any]] = []
    for i, player in enumerate(test.player.tolist()):
        tier, division = meta[player]
        top = np.argsort(-np.abs(contrib[i]))[:TOP_DRIVERS]
        players.append(
            {
                "id": ids[player],
                "region": REGIONS.get(player.split(":", 1)[0], player.split(":", 1)[0].upper()),
                "tier": tier,
                "division": division,
                "churn": round(float(preds["lightgbm"][i]), 4),
                "recency": round(float(preds["recency"][i]), 4),
                "churned": bool(test.y[i]),
                "games_28d": int(sum(test.x[i, FEATURES.index(f)] for f in FEATURES[:3])),
                "days_since_last_game": value(i, "days_since_last_game"),
                "win_rate": value(i, "win_rate"),
                "drivers": [
                    {
                        "feature": FEATURES[j],
                        "value": value(i, FEATURES[j]),
                        "effect": round(float(contrib[i, j]), 3),
                    }
                    for j in top
                ],
                "weeks": weeks.get(player, [0] * (WEEKS_BEFORE + WEEKS_AFTER)),
            }
        )
    players.sort(key=lambda p: p["id"])

    snapshot = {
        "meta": {
            "dataset": cfg.dataset,
            "cutoff": f"{cutoff:%Y-%m-%d}",
            "exported": now.isoformat(timespec="seconds"),
            "model": "LightGBM, Platt-calibrated (ADR 0008)",
            "players": len(players),
            "churn_rate": round(float(test.y.mean()), 4),
            "weeks": {"before": WEEKS_BEFORE, "after": WEEKS_AFTER},
            "note": "Frozen snapshot of held-out players, not a live product.",
        },
        "metrics": {
            name: {
                k: metrics["test"][name][k]
                for k in ("pr_auc", "pr_auc_ci", "roc_auc", "roc_auc_ci", "brier", "brier_ci")
            }
            for name in SHOWN
            if name in metrics["test"]
        },
        "vs_recency": {
            name: metrics["vs_baseline"][name]
            for name in SHOWN
            if name in metrics.get("vs_baseline", {}) and name != "majority"
        },
        "train": {k: metrics["data"]["train"][k] for k in ("examples", "players", "churn_rate")},
        "players": players,
    }
    path = snapshot_path(data_dir, cfg.dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=1) + "\n", encoding="utf-8")
    return ExportSummary(path=path, players=len(players), churned=int(test.y.sum()))
