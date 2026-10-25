"""The classical model ladder: majority class, recency rule, logistic regression, LightGBM.

Every model maps a feature matrix (columns in `FEATURES` order, NaN where missing) to a churn
probability. Logistic regression and LightGBM are calibrated with Platt scaling fitted on
out-of-fold predictions (ADR 0008). Saved models are plain numbers in JSON plus LightGBM's text
model, never pickles (docs/standards.md).
"""

import json
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from lolret.model.config import LightGBMParams
from lolret.model.data import FEATURES, Labels, Matrix, Vector
from lolret.model.evaluate import EPS, log_loss

MODEL_NAMES = ("majority", "recency", "logreg", "lightgbm")
MODELS_FILE = "models.json"
LIGHTGBM_FILE = "lightgbm.txt"

# Effectively no penalty, for the one- and two-parameter fits (recency rule, Platt scaling).
UNREGULARISED = 1e6

Fold = tuple[np.ndarray, np.ndarray]


def sigmoid(z: Vector) -> Vector:
    return 1.0 / (1.0 + np.exp(-z))


def logit(p: Vector) -> Vector:
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def signed_log1p(x: Matrix) -> Matrix:
    """log(1 + |x|) with x's sign: tames heavy tails (game counts, gaps) for a linear model."""
    return np.sign(x) * np.log1p(np.abs(x))


def player_folds(players: np.ndarray, n_folds: int, seed: int) -> list[Fold]:
    """Cross-validation folds inside the training set; a player's rows stay in one fold."""
    folds = GroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    return [(train, val) for train, val in folds.split(players, groups=players)]


@dataclass(frozen=True)
class Majority:
    """Predicts the training churn rate for everyone: the floor every model must clear."""

    rate: float

    @classmethod
    def fit(cls, y: Labels) -> "Majority":
        return cls(float(np.mean(y)))

    def predict(self, x: Matrix) -> Vector:
        return np.full(len(x), self.rate)


RECENCY_COLUMN = FEATURES.index("days_since_last_game")


@dataclass(frozen=True)
class Recency:
    """The recency rule: the longer since the last game, the likelier churn.

    It ranks players by days since their last game, so its PR-AUC and ROC-AUC are the raw
    rule's. A one-feature logistic regression on log(1 + days) turns the rank into a
    probability. Missing means the only recent game was still running at the cutoff: 0 days.
    """

    coef: float
    intercept: float

    @staticmethod
    def feature(x: Matrix) -> Vector:
        return np.log1p(np.nan_to_num(x[:, RECENCY_COLUMN], nan=0.0))

    @classmethod
    def fit(cls, x: Matrix, y: Labels) -> "Recency":
        lr = LogisticRegression(C=UNREGULARISED).fit(cls.feature(x)[:, None], y)
        return cls(float(lr.coef_[0, 0]), float(lr.intercept_[0]))

    def predict(self, x: Matrix) -> Vector:
        return sigmoid(self.coef * self.feature(x) + self.intercept)


@dataclass(frozen=True)
class LogReg:
    """L2 logistic regression.

    Inputs: signed log(1 + |x|) of every feature, NaN replaced by the training median, plus a
    missing-value indicator for each feature that had gaps in training, all standardised.
    """

    c: float
    medians: list[float]  # per feature, after the log transform
    indicators: list[int]  # positions in FEATURES that get a missing-value indicator
    mean: list[float]  # per design column
    scale: list[float]
    coef: list[float]
    intercept: float

    @staticmethod
    def _design(x: Matrix, medians: Vector, indicators: list[int]) -> Matrix:
        z = signed_log1p(x)
        missing = np.isnan(z)
        z = np.where(missing, medians, z)
        return np.hstack([z, missing[:, indicators].astype(np.float64)])

    @classmethod
    def fit(cls, x: Matrix, y: Labels, c: float) -> "LogReg":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN column; median set to 0
            medians = np.nan_to_num(np.nanmedian(signed_log1p(x), axis=0), nan=0.0)
        indicators = np.flatnonzero(np.isnan(x).any(axis=0)).tolist()
        design = cls._design(x, medians, indicators)
        mean = design.mean(axis=0)
        scale = design.std(axis=0)
        scale[scale == 0] = 1.0
        lr = LogisticRegression(C=c, max_iter=1000).fit((design - mean) / scale, y)
        return cls(
            c=c,
            medians=medians.tolist(),
            indicators=indicators,
            mean=mean.tolist(),
            scale=scale.tolist(),
            coef=lr.coef_[0].tolist(),
            intercept=float(lr.intercept_[0]),
        )

    def design_names(self) -> list[str]:
        return [*FEATURES, *(f"{FEATURES[i]}_missing" for i in self.indicators)]

    def predict(self, x: Matrix) -> Vector:
        design = self._design(x, np.asarray(self.medians), self.indicators)
        z = (design - np.asarray(self.mean)) / np.asarray(self.scale)
        return sigmoid(z @ np.asarray(self.coef) + self.intercept)


def select_logreg(
    x: Matrix, y: Labels, folds: list[Fold], cs: list[float]
) -> tuple[float, Vector, dict[str, float]]:
    """Pick C by out-of-fold log loss. Returns C, its out-of-fold predictions, loss per C."""
    oofs: dict[float, Vector] = {}
    for c in cs:
        oofs[c] = np.empty(len(y))
        for train, val in folds:
            oofs[c][val] = LogReg.fit(x[train], y[train], c).predict(x[val])
    losses = {c: log_loss(y, oof) for c, oof in oofs.items()}
    best = min(cs, key=losses.__getitem__)
    return best, oofs[best], {str(c): loss for c, loss in losses.items()}


def lightgbm_params(params: LightGBMParams, seed: int) -> dict[str, Any]:
    return {
        "objective": "binary",
        "learning_rate": params.learning_rate,
        "num_leaves": params.num_leaves,
        "min_child_samples": params.min_child_samples,
        "feature_fraction": params.feature_fraction,
        "bagging_fraction": params.bagging_fraction,
        "bagging_freq": 1,
        "lambda_l2": params.lambda_l2,
        "seed": seed,
        "deterministic": True,
        "force_row_wise": True,
        "verbosity": -1,
    }


@dataclass(frozen=True)
class GBM:
    """LightGBM on the raw features; it handles missing values natively."""

    booster: lgb.Booster

    @classmethod
    def fit(
        cls,
        x: Matrix,
        y: Labels,
        params: LightGBMParams,
        rounds: int,
        seed: int,
        names: Sequence[str] = FEATURES,
    ) -> "GBM":
        data = lgb.Dataset(x, y, feature_name=list(names))
        return cls(lgb.train(lightgbm_params(params, seed), data, num_boost_round=rounds))

    def predict(self, x: Matrix) -> Vector:
        return np.asarray(self.booster.predict(x), dtype=np.float64)


def cv_lightgbm(
    x: Matrix,
    y: Labels,
    folds: list[Fold],
    params: LightGBMParams,
    seed: int,
    names: Sequence[str] = FEATURES,
) -> tuple[Vector, int]:
    """Early-stop on each fold. Returns out-of-fold predictions and the mean best round count."""
    oof = np.empty(len(y))
    rounds: list[int] = []
    for train, val in folds:
        train_set = lgb.Dataset(x[train], y[train], feature_name=list(names))
        val_set = lgb.Dataset(x[val], y[val], reference=train_set)
        booster = lgb.train(
            lightgbm_params(params, seed),
            train_set,
            num_boost_round=params.max_rounds,
            valid_sets=[val_set],
            callbacks=[lgb.early_stopping(params.early_stopping_rounds, verbose=False)],
        )
        best = max(booster.best_iteration, 1)
        rounds.append(best)
        oof[val] = np.asarray(booster.predict(x[val], num_iteration=best), dtype=np.float64)
    return oof, max(round(float(np.mean(rounds))), 1)


@dataclass(frozen=True)
class Platt:
    """Platt scaling: a logistic regression on the logit of a model's probability."""

    a: float
    b: float

    @classmethod
    def fit(cls, p: Vector, y: Labels) -> "Platt":
        lr = LogisticRegression(C=UNREGULARISED).fit(logit(p)[:, None], y)
        return cls(float(lr.coef_[0, 0]), float(lr.intercept_[0]))

    def apply(self, p: Vector) -> Vector:
        return sigmoid(self.a * logit(p) + self.b)


@dataclass(frozen=True)
class Ladder:
    """The fitted models, saved together as `models.json` + `lightgbm.txt`."""

    majority: Majority
    recency: Recency
    logreg: LogReg
    logreg_platt: Platt
    lightgbm: GBM
    lightgbm_platt: Platt

    def predict(self, x: Matrix) -> dict[str, Vector]:
        """Calibrated churn probability from every model, keyed by `MODEL_NAMES`."""
        return {
            "majority": self.majority.predict(x),
            "recency": self.recency.predict(x),
            "logreg": self.logreg_platt.apply(self.logreg.predict(x)),
            "lightgbm": self.lightgbm_platt.apply(self.lightgbm.predict(x)),
        }

    def save(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        params = {
            "features": list(FEATURES),
            "majority": asdict(self.majority),
            "recency": asdict(self.recency),
            "logreg": asdict(self.logreg),
            "logreg_platt": asdict(self.logreg_platt),
            "lightgbm_platt": asdict(self.lightgbm_platt),
        }
        (out_dir / MODELS_FILE).write_text(json.dumps(params, indent=2) + "\n", encoding="utf-8")
        self.lightgbm.booster.save_model(out_dir / LIGHTGBM_FILE)

    @classmethod
    def load(cls, out_dir: Path) -> "Ladder":
        params = json.loads((out_dir / MODELS_FILE).read_text(encoding="utf-8"))
        if params["features"] != list(FEATURES):
            raise ValueError(
                f"{out_dir / MODELS_FILE} was trained on a different feature list; retrain it"
            )
        return cls(
            majority=Majority(**params["majority"]),
            recency=Recency(**params["recency"]),
            logreg=LogReg(**params["logreg"]),
            logreg_platt=Platt(**params["logreg_platt"]),
            lightgbm=GBM(lgb.Booster(model_file=out_dir / LIGHTGBM_FILE)),
            lightgbm_platt=Platt(**params["lightgbm_platt"]),
        )
