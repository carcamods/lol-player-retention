"""Test-set metrics with bootstrap intervals, reliability bins and feature importance.

PR-AUC is the headline metric: churners are the minority, and a random ranking scores the
churn rate. ROC-AUC, Brier score and log loss are reported alongside (ADR 0008).
"""

from typing import Any

import lightgbm as lgb
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from lolret.model.data import FEATURES, Labels, Matrix, Vector

EPS = 1e-6
RANK_METRICS = ("pr_auc", "roc_auc")
METRICS = (*RANK_METRICS, "brier", "log_loss")


def brier(y: Labels, p: Vector) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(y: Labels, p: Vector) -> float:
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def scores(y: Labels, p: Vector) -> dict[str, float | None]:
    """All metrics; the ranking metrics are None unless both classes are present."""
    both = 0 < int(y.sum()) < len(y)
    return {
        "pr_auc": float(average_precision_score(y, p)) if both else None,
        "roc_auc": float(roc_auc_score(y, p)) if both else None,
        "brier": brier(y, p),
        "log_loss": log_loss(y, p),
    }


def evaluate(
    y: Labels, preds: dict[str, Vector], *, baseline: str, n_boot: int, seed: int
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Point metrics with 95% bootstrap intervals for every model, and each model's PR-AUC
    difference from `baseline` on the same resamples (a paired comparison).

    Each test row is a different player, so resampling rows resamples players.
    """
    point = {name: scores(y, p) for name, p in preds.items()}
    rng = np.random.default_rng(seed)
    draws: dict[str, dict[str, list[float]]] = {
        name: {metric: [] for metric in METRICS} for name in preds
    }
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if not 0 < int(y[idx].sum()) < len(idx):
            continue  # a resample with one class has no PR-AUC
        for name, p in preds.items():
            for metric, value in scores(y[idx], p[idx]).items():
                if value is not None:
                    draws[name][metric].append(value)

    def interval(values: list[float]) -> list[float] | None:
        return np.percentile(values, [2.5, 97.5]).tolist() if values else None

    results: dict[str, dict[str, Any]] = {}
    for name in preds:
        results[name] = {}
        for metric in METRICS:
            results[name][metric] = point[name][metric]
            results[name][f"{metric}_ci"] = interval(draws[name][metric])

    comparison: dict[str, dict[str, Any]] = {}
    base_point, base_draws = point[baseline]["pr_auc"], draws[baseline]["pr_auc"]
    for name in preds:
        model_point = point[name]["pr_auc"]
        if name == baseline or model_point is None or base_point is None:
            continue
        diffs = [a - b for a, b in zip(draws[name]["pr_auc"], base_draws, strict=True)]
        comparison[name] = {
            "pr_auc_diff": model_point - base_point,
            "pr_auc_diff_ci": interval(diffs),
        }
    return results, comparison


def reliability(y: Labels, p: Vector, bins: int = 10) -> list[dict[str, float]]:
    """Equal-count bins by predicted probability: mean prediction vs observed churn rate."""
    order = np.argsort(p, kind="stable")
    return [
        {"predicted": float(p[i].mean()), "observed": float(y[i].mean()), "n": len(i)}
        for i in np.array_split(order, min(bins, len(p)))
        if len(i)
    ]


def lightgbm_importance(booster: lgb.Booster, x: Matrix) -> dict[str, float]:
    """Mean |SHAP value| per feature (log-odds), from LightGBM's built-in TreeSHAP."""
    contrib = np.asarray(booster.predict(x, pred_contrib=True), dtype=np.float64)
    mean_abs = np.abs(contrib[:, :-1]).mean(axis=0)  # the last column is the bias
    ranked = sorted(zip(FEATURES, mean_abs.tolist(), strict=True), key=lambda kv: -kv[1])
    return dict(ranked)
