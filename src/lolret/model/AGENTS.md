# `lolret.model`: classical models and evaluation

Trains the Phase 4a ladder (majority class, recency rule, logistic regression, LightGBM) on
`examples.parquet` and evaluates it on held-out players at the latest cutoff. Design: ADR 0008.

**Status:** done. First results on run `v1` (2026-10-24) are in the README: no model clearly
beats the recency rule yet. A test set with fewer than 200 churners marks the model card
"Preliminary".

## Files

- `config.py`: `TrainConfig` from `configs/train.yaml`.
- `data.py`: `FEATURES` (matrix column order = `features.sql` order), `load_examples` (eligible
  and labelled rows, NULL to NaN; `labelled=False` keeps unlabelled rows with `y = UNKNOWN`),
  `in_test_set`, `split_by_player_and_time`.
- `models.py`: `Majority`, `Recency`, `LogReg`, `GBM`, `Platt`, `player_folds`,
  `select_logreg`, `cv_lightgbm`, and `Ladder` (predict, save, load).
- `evaluate.py`: `scores`, `evaluate` (bootstrap intervals and the paired difference from the
  baseline), `by_group` (scores per region and tier, reporting only), `reliability`,
  `lightgbm_importance`.
- `train.py`: `fit_ladder` (selection, calibration and fitting; also used by the forward test)
  and `train_and_evaluate`, which writes `data/models/<dataset>/`: `models.json`,
  `lightgbm.txt`, `metrics.json`, `model_card.md`.
- `card.py`: `render_model_card` from the metrics dict.
- `candidates.py`: `CANDIDATES`, `load_candidates`, `CandidateGBM` (LightGBM on the 21
  features plus the candidates, same protocol) and `evaluate_candidates` (ADR 0013).

## Rules that must not break

- **The test set chooses nothing.** Model selection and Platt scaling use only player-grouped
  out-of-fold predictions inside training.
- **A player's side comes from a hash of the player alone** (`in_test_set`). Don't switch to a
  random split of the current rows, or the test set changes as data arrives.
- `FEATURES` equals the feature columns of `features.sql`, in order (a test enforces it). To add
  a feature, change the dataset first (see its `AGENTS.md`), then `FEATURES`. Old `models.json`
  files then refuse to load.
- No pickles: `models.json` plus LightGBM's text model. Nothing written may identify a player
  (a test checks the outputs for the synthetic puuids).
- Ladder fields (tier, division, LP, wins) are never features (ADR 0006).

## Pitfalls

- The package is `model`, not `models`: `.gitignore` ignores every `models/` directory.
- Reliability bins are equal-count. With tied predictions (a constant model) the bins are
  arbitrary.
- scikit-learn ships no type stubs; `pyproject.toml` has a mypy override.
- Run `v1`'s test set has 200 churners, so PR-AUC intervals are about +/-0.07 wide. Differences
  between models smaller than that aren't resolvable; say so rather than ranking them.

## Tests

`tests/test_model.py`: the feature-list drift guard, loading, split properties, each model,
Platt scaling, bootstrap, reliability, train and reload end to end, no identifiers in the
outputs, and the CLI. Runs in about 5 seconds.
