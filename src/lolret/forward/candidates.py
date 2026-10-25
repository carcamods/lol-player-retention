"""Enter the candidate features in the forward test as a later entry (ADR 0013).

A LightGBM on the 21 features plus the candidates, retrained like the ladder on every labelled
example of the base run, predicts for the same eligible players at the forward cutoff. It
must be frozen after the ladder's hash is committed and before any label is collected. The
forward test then decides whether the candidates join the model.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from lolret.forward.collect import labels_store_path, open_base, open_features, require_complete
from lolret.forward.config import Forward, ForwardError
from lolret.forward.predict import (
    EXAMPLES_FILE,
    LADDER,
    MANIFEST_FILE,
    build_forward_examples,
    entry_path,
    forward_dir,
    pending_path,
    verified_entries,
    write_entry,
)
from lolret.log import get_logger
from lolret.model.candidates import MODEL, CandidateGBM, candidates_path, with_candidates
from lolret.model.data import load_examples
from lolret.model.train import examples_path, sha256

log = get_logger(__name__)

ENTRY = "candidates"
WORK_DIR = "candidates"


@dataclass(frozen=True)
class CandidatesEntry:
    entry: Path
    sha256: str
    players: int
    rounds: int


def freeze_candidates_entry(fwd: Forward, data_dir: Path, *, now: datetime) -> CandidatesEntry:
    out_dir = forward_dir(data_dir, fwd)
    entry = entry_path(data_dir, fwd, ENTRY)
    if labels_store_path(data_dir, fwd).exists():
        raise ForwardError("labels were already collected; entries must be frozen before")
    if entry.exists():
        raise ForwardError(f"the candidates are already frozen in {entry}; never redone")
    if LADDER not in verified_entries(fwd, data_dir):
        raise ForwardError("freeze the ladder and commit its hash before entering candidates")

    work = out_dir / WORK_DIR
    base = open_base(data_dir, fwd)
    store = open_features(data_dir, fwd, base, read_only=True)
    try:
        require_complete(store, fwd.collect.platforms, "features")
        forward = build_forward_examples(
            store,
            fwd,
            work / EXAMPLES_FILE,
            until=fwd.cutoff,
            candidates=work / "candidates.parquet",
        )
    finally:
        store.close()
        base.close()
    frozen = load_examples(out_dir / EXAMPLES_FILE, labelled=False)
    same = np.array_equal(forward.player, frozen.player)
    if not (same and np.array_equal(forward.x, frozen.x, equal_nan=True)):
        raise ForwardError("the features at the cutoff differ from the ones the ladder used")

    train = load_examples(examples_path(data_dir, fwd.train.dataset))
    train_x = with_candidates(train, candidates_path(data_dir, fwd.train.dataset))
    log.info("Training LightGBM with the candidates on %d examples.", len(train))
    model = CandidateGBM.fit(train_x, train.y, train.player, fwd.train)
    preds = {MODEL: model.predict(with_candidates(forward, work / "candidates.parquet"))}
    model.gbm.booster.save_model(work / "lightgbm_candidates.txt")
    pending = pending_path(entry)
    write_entry(pending, forward.player, preds)
    digest = sha256(pending)

    manifest_path = out_dir / MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"][ENTRY] = {
        "file": f"entries/{entry.name}",
        "sha256": digest,
        "frozen_at": now.isoformat(timespec="seconds"),
        "rounds": model.rounds,
        "platt": [model.platt.a, model.platt.b],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pending.replace(entry)  # last: a run that fails before this line can simply run again
    return CandidatesEntry(entry=entry, sha256=digest, players=len(forward), rounds=model.rounds)
