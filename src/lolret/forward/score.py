"""Score the forward test once its label window has happened (ADR 0011).

Before any metric, three checks: every entry file still has its committed hash, the labels
collection finished, and rebuilding the features with the labels collected gives exactly the
frozen features. Then every model is compared with the recency rule on the same bootstrap
resamples. The question set before the predictions were frozen: does LightGBM beat the recency
rule, that is, does the 95% interval of the PR-AUC difference exclude zero?

Output, in `data/forward/<name>/`: `labelled.parquet`, `results.json` and `report.md`.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from lolret.collect.store import LayeredStore
from lolret.forward.collect import (
    labels_store_path,
    open_base,
    open_features,
    require_complete,
)
from lolret.forward.config import Forward, ForwardError
from lolret.forward.predict import (
    EXAMPLES_FILE,
    MANIFEST_FILE,
    build_forward_examples,
    forward_dir,
    read_entry,
    verified_entries,
)
from lolret.model.card import LABELS, verdict, with_ci
from lolret.model.data import UNKNOWN, Vector, load_examples
from lolret.model.evaluate import evaluate, reliability

BASELINE = "recency"
PRIMARY = "lightgbm"  # the pre-registered comparison: PRIMARY against BASELINE
LADDER_MODELS = ("majority", "recency", "logreg", "lightgbm")
LABELLED_FILE = "labelled.parquet"
RESULTS_FILE = "results.json"
REPORT_FILE = "report.md"


@dataclass(frozen=True)
class ScoreSummary:
    out_dir: Path
    players: int
    churned: int
    results: dict[str, dict[str, Any]]
    vs_baseline: dict[str, dict[str, Any]]


def _aligned_predictions(entries: dict[str, Path], players: np.ndarray) -> dict[str, Vector]:
    row = {p: i for i, p in enumerate(players.tolist())}
    preds: dict[str, Vector] = {}
    for entry, path in entries.items():
        entry_players, entry_preds = read_entry(path)
        if set(entry_players.tolist()) != set(row):
            raise ForwardError(f"entry '{entry}' doesn't predict for exactly the eligible players")
        idx = np.array([row[p] for p in entry_players.tolist()])
        for name, values in entry_preds.items():
            if name in preds:
                raise ForwardError(f"model '{name}' appears in more than one entry")
            preds[name] = np.empty(len(players))
            preds[name][idx] = values
    if BASELINE not in preds:
        raise ForwardError(f"no entry has the '{BASELINE}' baseline")
    return preds


def render_report(m: dict[str, Any]) -> str:
    def label(name: str) -> str:
        return LABELS.get(name, name)

    lines = [
        f"# Forward test `{m['name']}`",
        "",
        f"Predictions for {m['cutoff']}, frozen {m['frozen_at'][:10]} (commit "
        f"`{(m['git_commit'] or 'unknown')[:7]}`) before any outcome was collected; outcomes "
        f"observed to {m['label_window_end']}; scored {m['scored_at'][:10]}.",
        "",
        f"{m['players']:,} players were eligible at the cutoff and {m['churned']:,} of them "
        f"({m['churned'] / m['players']:.1%}) didn't play in the next 28 days.",
        "",
        "| Model | PR-AUC (95% CI) | ROC-AUC (95% CI) | Brier (95% CI) |",
        "|---|---|---|---|",
    ]
    for name, r in m["results"].items():
        lines.append(
            f"| {label(name)} | {with_ci(r['pr_auc'], r['pr_auc_ci'])} | "
            f"{with_ci(r['roc_auc'], r['roc_auc_ci'])} | {with_ci(r['brier'], r['brier_ci'])} |"
        )
    lines += ["", "**The question set before freezing:**", ""]
    if PRIMARY in m["vs_baseline"]:
        lines.append(verdict(PRIMARY, m["vs_baseline"][PRIMARY], BASELINE))
    others = [n for n in m["vs_baseline"] if n != PRIMARY]
    if others:
        lines += ["", "Other comparisons with the recency rule:", ""]
        lines += [verdict(n, m["vs_baseline"][n], BASELINE) for n in others]
    if m.get("vs_lightgbm"):
        lines += ["", "Later entries against LightGBM:", ""]
        for name, c in m["vs_lightgbm"].items():
            lo, hi = c["pr_auc_diff_ci"] or (float("nan"), float("nan"))
            lines.append(
                f"- {label(name)}: {c['pr_auc_diff']:+.3f} PR-AUC (95% CI {lo:+.3f} to {hi:+.3f})."
            )
    return "\n".join(lines) + "\n"


def score_forward(fwd: Forward, data_dir: Path, *, now: datetime) -> ScoreSummary:
    entries = verified_entries(fwd, data_dir)
    out_dir = forward_dir(data_dir, fwd)
    labels_path = labels_store_path(data_dir, fwd)
    if not labels_path.exists():
        raise ForwardError(
            f"no labels yet: run `lolret forward collect --labels` after "
            f"{fwd.label_window_end:%Y-%m-%d %H:%M} UTC"
        )
    base = open_base(data_dir, fwd)
    features = open_features(data_dir, fwd, base, read_only=True)
    store = LayeredStore(labels_path, [features, base], read_only=True)
    try:
        require_complete(store, fwd.collect.platforms, "labels")
        labelled = build_forward_examples(store, fwd, out_dir / LABELLED_FILE, until=None)
    finally:
        store.close()
        features.close()
        base.close()

    frozen = load_examples(out_dir / EXAMPLES_FILE, labelled=False)
    same_rows = np.array_equal(labelled.player, frozen.player)
    if not (same_rows and np.array_equal(labelled.x, frozen.x, equal_nan=True)):
        raise ForwardError("rebuilding the features with the labels collected changed them")
    if (labelled.y == UNKNOWN).any():
        raise ForwardError("some eligible players still have no label")

    preds = _aligned_predictions(entries, labelled.player)
    common = {"n_boot": fwd.train.bootstrap, "seed": fwd.train.seed}
    results, vs_baseline = evaluate(labelled.y, preds, baseline=BASELINE, **common)
    later = [name for name in preds if name not in LADDER_MODELS]
    vs_lightgbm: dict[str, dict[str, Any]] = {}
    if later and PRIMARY in preds:
        _, against = evaluate(labelled.y, preds, baseline=PRIMARY, **common)
        vs_lightgbm = {name: against[name] for name in later if name in against}
    manifest = json.loads((out_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    metrics: dict[str, Any] = {
        "name": fwd.name,
        "cutoff": manifest["cutoff"],
        "label_window_end": manifest["label_window_end"],
        "frozen_at": manifest["frozen_at"],
        "git_commit": manifest["git_commit"],
        "entries": dict(fwd.cfg.entries),
        "scored_at": now.isoformat(timespec="seconds"),
        "players": len(labelled),
        "churned": int(labelled.y.sum()),
        "baseline": BASELINE,
        "primary": PRIMARY,
        "results": results,
        "vs_baseline": vs_baseline,
        "vs_lightgbm": vs_lightgbm,
        "reliability": {name: reliability(labelled.y, p) for name, p in preds.items()},
    }
    (out_dir / RESULTS_FILE).write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (out_dir / REPORT_FILE).write_text(render_report(metrics), encoding="utf-8")
    return ScoreSummary(
        out_dir=out_dir,
        players=len(labelled),
        churned=int(labelled.y.sum()),
        results=results,
        vs_baseline=vs_baseline,
    )
