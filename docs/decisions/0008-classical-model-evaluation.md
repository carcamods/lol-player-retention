# 0008: Classical models: split, calibration and comparison with the baseline

**Status:** Accepted, 2026-10-22

## Context

FR3 asks for a majority-class baseline, a recency rule, logistic regression and LightGBM,
compared on a temporal, player-grouped holdout, with calibrated probabilities, saved without
pickles. Several details were still open:

- how the split is both "by player" and "by time";
- how to choose hyperparameters and calibrate without touching the test set;
- how each model handles the deliberate NULLs in the dataset (`docs/features.md`);
- how to make "beats the recency baseline" a claim with an interval, not a single number.

Run `v1` should give about 11-12k eligible examples over three cutoffs (ADR 0006), so the test
set holds roughly a thousand examples, and every metric needs an interval.

## Decision

**Split.** A player is held out for testing if `sha256("<seed>:<platform>:<puuid>")` falls
below `test_fraction` (0.3). Test: the held-out players at the latest cutoff. Train: all other
players at the earlier cutoffs. Two kinds of rows are not used: training players at the latest
cutoff (their labels fall in the same window as the test labels) and held-out players at
earlier cutoffs (the same person would be in training and test). The hash depends only on the
player, so a player's side never changes as the dataset grows.

**Selection and calibration use the training set only.** Five player-grouped folds
(`GroupKFold`, shuffled, seeded):

- Logistic regression: C from `[0.001, 0.003, 0.01, 0.03, 0.1, 1, 10]`, chosen by
  out-of-fold log loss. The first grid started at 0.01, and run `v1` picked that edge, so
  the grid was widened; it now picks 0.03, and the loss is almost flat from 0.01 to 10.
- LightGBM: fixed parameters (`configs/train.yaml`), early stopping on each fold; the final
  model uses the mean best round count.
- Both are Platt-scaled, fitted on their out-of-fold predictions, then refitted on all
  training rows.

**Baselines.** Majority class predicts the training churn rate. The recency rule ranks by
`days_since_last_game` (NULL means a game was in progress at T, so it counts as 0); a
one-feature logistic fit on log(1 + days) gives it a probability without changing its ranking.

**Missing values.** Logistic regression: signed log(1 + |x|), training-median imputation, a
missing-value indicator for every feature with gaps in training, standardisation. LightGBM
handles NaN natively.

**Metrics.** PR-AUC is the headline; ROC-AUC, Brier score and log loss sit beside it. 95%
percentile bootstrap intervals, 1,000 resamples of test rows (one row per player). A model
"beats" the recency rule only if the paired bootstrap interval of its PR-AUC difference
excludes zero. Calibration is reported as 10 equal-count reliability bins. Feature importance
is mean |SHAP| from LightGBM's built-in TreeSHAP (`pred_contrib`), so no `shap` dependency.

**Artifacts.** `data/models/<dataset>/`: `models.json` (feature list, baseline, logistic and
Platt parameters), `lightgbm.txt`, `metrics.json` (with the config and the SHA-256 of
`examples.parquet`) and `model_card.md`. No pickles and no player identifiers. The package is
`lolret.model`, singular, because `.gitignore` ignores every `models/` directory.

## Consequences

- About 43% of eligible rows go unused (if each cutoff holds a third of them, training uses
  0.7 x 2/3 and testing 0.3 x 1/3). That is the price of a test set that is new in both players
  and time.
- At pilot rates the test set has about 1,100 examples and 250 churners. Small differences
  between models won't be resolvable, and the model card says so.
- If the churn rate shifts between cutoffs, the calibrators (fitted on earlier cutoffs) will be
  off on the test cutoff. That is what deployment would face, so it is reported, not corrected.
- Cross-fitted Platt scaling slightly under-states the final models' confidence, because they
  are refitted on more data than each fold saw.
- The neural nets (Phase 4b) reuse the same split, folds and `evaluate()`.
- LightGBM parameters are fixed, not searched. A search can be added on the same folds later.
