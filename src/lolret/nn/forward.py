"""Enter the neural nets in the forward test as a later entry (ADR 0011, ADR 0012 rule 4).

Like the ladder entry, the nets are retrained on every labelled example of the base run (all
players, every cutoff) with the settings in `configs/train_nn.yaml`, and predict for the same
eligible players at the forward cutoff. The LightGBM half of the average comes from the frozen
ladder entry, so the ladder's hash must already be committed. Nothing runs once labels exist.

Output: `entries/nn.csv` (MLP, GRU, LightGBM + GRU average) and the nets in `nn/`, next to the
ladder entry in `data/forward/<name>/`.
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
    read_entry,
    verified_entries,
    write_entry,
)
from lolret.log import get_logger
from lolret.model.data import load_examples
from lolret.model.models import player_folds
from lolret.model.train import examples_path, sha256
from lolret.nn.config import NNConfig
from lolret.nn.data import load_sequences, sequences_path
from lolret.nn.train import AVERAGE, KINDS, NN_DIR, NN_FILE, train_kind

log = get_logger(__name__)

NETS = "nn"


@dataclass(frozen=True)
class NetsEntry:
    entry: Path
    sha256: str
    players: int


def freeze_nn_entry(fwd: Forward, cfg: NNConfig, data_dir: Path, *, now: datetime) -> NetsEntry:
    out_dir = forward_dir(data_dir, fwd)
    entry = entry_path(data_dir, fwd, NETS)
    if labels_store_path(data_dir, fwd).exists():
        raise ForwardError("labels were already collected; entries must be frozen before")
    if entry.exists():
        raise ForwardError(f"the nets are already frozen in {entry}; they are never redone")
    ladder = verified_entries(fwd, data_dir).get(LADDER)
    if ladder is None:
        raise ForwardError("freeze the ladder and commit its hash before entering the nets")

    base = open_base(data_dir, fwd)
    store = open_features(data_dir, fwd, base, read_only=True)
    work = out_dir / NN_DIR
    try:
        require_complete(store, fwd.collect.platforms, "features")
        forward = build_forward_examples(
            store,
            fwd,
            work / EXAMPLES_FILE,
            until=fwd.cutoff,
            sequences=work / "sequences.parquet",
        )
    finally:
        store.close()
        base.close()
    frozen = load_examples(out_dir / EXAMPLES_FILE, labelled=False)
    same = np.array_equal(forward.player, frozen.player)
    if not (same and np.array_equal(forward.x, frozen.x, equal_nan=True)):
        raise ForwardError("the features at the cutoff differ from the ones the ladder used")
    seq, lengths = load_sequences(work / "sequences.parquet", forward)

    train = load_examples(examples_path(data_dir, fwd.train.dataset))
    train_seq, train_len = load_sequences(sequences_path(data_dir, fwd.train.dataset), train)
    folds = player_folds(train.player, fwd.train.cv_folds, fwd.train.seed)
    log.info("Training the nets on %d examples for the forward test.", len(train))
    nets = {
        kind: train_kind(kind, train, train_seq, train_len, folds, cfg, fwd.train.seed)
        for kind in KINDS
    }
    preds = {kind: n.predict(forward.x, seq, lengths) for kind, n in nets.items()}

    ladder_players, ladder_preds = read_entry(ladder)
    row = {p: i for i, p in enumerate(ladder_players.tolist())}
    lightgbm = ladder_preds["lightgbm"][[row[p] for p in forward.player.tolist()]]
    preds[AVERAGE] = (lightgbm + preds["gru"]) / 2

    saved = {kind: n.save(work) for kind, n in nets.items()}
    (work / NN_FILE).write_text(
        json.dumps({"config": cfg.model_dump(mode="json"), "models": saved}, indent=2) + "\n",
        encoding="utf-8",
    )
    write_entry(entry, forward.player, preds)
    digest = sha256(entry)
    manifest_path = out_dir / MANIFEST_FILE
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"][NETS] = {
        "file": f"entries/{entry.name}",
        "sha256": digest,
        "frozen_at": now.isoformat(timespec="seconds"),
        "nets": {kind: {"epochs": n.epochs} for kind, n in nets.items()},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return NetsEntry(entry=entry, sha256=digest, players=len(forward))
