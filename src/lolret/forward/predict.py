"""Freeze the forward test's predictions (ADR 0011).

The ladder is trained on every labelled example of the base run: all players at every cutoff,
each label known by the forward cutoff. Features at the forward cutoff come from the features
store, and every eligible player gets one probability per model. The file's SHA-256 goes into
`configs/forward.yaml` and is committed before any label is collected; scoring refuses a file
whose hash differs.

Output, in `data/forward/<name>/`: `examples.parquet` (features at the cutoff),
`entries/<entry>.csv`, the models, and `manifest.json`. The entry files hold PUUIDs, so they
stay under `data/` like everything else; only their hashes are published.
"""

import csv
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from lolret import __version__
from lolret.collect.store import Store
from lolret.dataset.build import build_examples
from lolret.dataset.extract import extract
from lolret.forward.collect import (
    labels_store_path,
    open_base,
    open_features,
    require_complete,
)
from lolret.forward.config import Forward, ForwardError
from lolret.log import get_logger
from lolret.model.data import Examples, Vector, load_examples
from lolret.model.models import LIGHTGBM_FILE, MODELS_FILE
from lolret.model.train import describe, examples_path, fit_ladder, sha256

log = get_logger(__name__)

LADDER = "ladder"
EXAMPLES_FILE = "examples.parquet"
MANIFEST_FILE = "manifest.json"


def forward_dir(data_dir: Path, fwd: Forward) -> Path:
    return data_dir / "forward" / fwd.name


def entry_path(data_dir: Path, fwd: Forward, entry: str) -> Path:
    return forward_dir(data_dir, fwd) / "entries" / f"{entry}.csv"


def build_forward_examples(
    store: Store, fwd: Forward, path: Path, *, until: datetime | None
) -> Examples:
    """Features (and, with `until=None`, labels) at the forward cutoff, written to `path`."""
    tables = extract(store, fwd.collect, until=until)
    with duckdb.connect() as con:
        build_examples(con, tables, [fwd.cutoff])
        path.parent.mkdir(parents=True, exist_ok=True)
        con.table("examples").write_parquet(str(path))
    return load_examples(path, labelled=False)


def write_entry(path: Path, players: np.ndarray, preds: dict[str, Vector]) -> None:
    """One row per player, sorted: platform, puuid, then a probability per model."""
    path.parent.mkdir(parents=True, exist_ok=True)
    order = np.argsort(players, kind="stable")
    with path.open("w", encoding="utf-8", newline="\n") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["platform", "puuid", *preds])
        for i in order:
            platform, puuid = str(players[i]).split(":", 1)
            writer.writerow([platform, puuid, *(f"{p[i]:.6f}" for p in preds.values())])


def read_entry(path: Path) -> tuple[np.ndarray, dict[str, Vector]]:
    """Players ("platform:puuid") and each model's probabilities, as written."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    players = np.array([f"{r[0]}:{r[1]}" for r in body], dtype=np.str_)
    preds = {
        name: np.array([float(r[j]) for r in body]) for j, name in enumerate(header[2:], start=2)
    }
    return players, preds


def verified_entries(fwd: Forward, data_dir: Path) -> dict[str, Path]:
    """Every entry named in the config, after checking its file still has the committed hash."""
    if not fwd.cfg.entries:
        raise ForwardError(
            "no frozen entries in the config: run `lolret forward predict`, then commit the "
            "printed hash in the config before collecting labels"
        )
    paths: dict[str, Path] = {}
    for entry, expected in fwd.cfg.entries.items():
        path = entry_path(data_dir, fwd, entry)
        if not path.exists():
            raise ForwardError(f"entry '{entry}' has no file at {path}")
        if sha256(path) != expected:
            raise ForwardError(f"{path} doesn't match the SHA-256 committed for '{entry}'")
        paths[entry] = path
    return paths


def frozen_players(fwd: Forward, data_dir: Path) -> set[str]:
    """The players every frozen entry predicts for ("platform:puuid")."""
    players: set[str] = set()
    for path in verified_entries(fwd, data_dir).values():
        players |= set(read_entry(path)[0].tolist())
    return players


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


@dataclass(frozen=True)
class FreezeSummary:
    entry: Path
    sha256: str
    players: int
    churn_expected: float  # mean calibrated LightGBM probability
    train_rows: int


def freeze_predictions(fwd: Forward, data_dir: Path, *, now: datetime) -> FreezeSummary:
    out_dir = forward_dir(data_dir, fwd)
    entry = entry_path(data_dir, fwd, LADDER)
    if labels_store_path(data_dir, fwd).exists():
        raise ForwardError("labels were already collected; predictions must be frozen before")
    if entry.exists():
        raise ForwardError(f"predictions are already frozen in {entry}; they are never redone")

    base = open_base(data_dir, fwd)
    store = open_features(data_dir, fwd, base, read_only=True)
    try:
        require_complete(store, fwd.collect.platforms, "features")
        forward = build_forward_examples(store, fwd, out_dir / EXAMPLES_FILE, until=fwd.cutoff)
    finally:
        store.close()
        base.close()

    source = examples_path(data_dir, fwd.train.dataset)
    train = load_examples(source)
    window = timedelta(days=fwd.base.label_window_days)
    last_label = train.cutoff.max().item().replace(tzinfo=UTC) + window
    if last_label > fwd.cutoff:
        raise ForwardError(f"a training label is only known on {last_label:%Y-%m-%d}")
    log.info(
        "Training on %d examples (%d players); predicting for %d eligible players at %s.",
        len(train),
        len(np.unique(train.player)),
        len(forward),
        f"{fwd.cutoff:%Y-%m-%d}",
    )
    ladder, selection = fit_ladder(train, fwd.train)
    preds = ladder.predict(forward.x)
    ladder.save(out_dir)
    write_entry(entry, forward.player, preds)
    digest = sha256(entry)

    manifest: dict[str, Any] = {
        "name": fwd.name,
        "cutoff": f"{fwd.cutoff:%Y-%m-%d}",
        "label_window_end": f"{fwd.label_window_end:%Y-%m-%d}",
        "frozen_at": now.isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "lolret_version": __version__,
        "train_config": fwd.train.model_dump(),
        "train_data": describe(train) | {"examples_sha256": sha256(source)},
        "selection": selection,
        "forward_examples": {
            "eligible": len(forward),
            "sha256": sha256(out_dir / EXAMPLES_FILE),
        },
        "models_sha256": {name: sha256(out_dir / name) for name in (MODELS_FILE, LIGHTGBM_FILE)},
        "entries": {LADDER: {"file": f"entries/{entry.name}", "sha256": digest}},
    }
    (out_dir / MANIFEST_FILE).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return FreezeSummary(
        entry=entry,
        sha256=digest,
        players=len(forward),
        churn_expected=float(np.mean(preds["lightgbm"])),
        train_rows=len(train),
    )
