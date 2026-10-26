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
- Tuning LightGBM barely helps. A 40-setting random search inside training (2026-10-25)
  improved out-of-fold log loss by 0.001-0.002 and PR-AUC by 0.000-0.007 on fresh folds: noise.
  The hand-set parameters stay; never tune on the test set.
- Run `v1`'s test set has 200 churners, so PR-AUC intervals are about +/-0.07 wide. Differences
  between models smaller than that aren't resolvable; say so rather than ranking them.
- PR-AUC isn't comparable across groups with different churn: in training, Bronze churns 26.5%
  and Diamond 7.3% (others 17-24%; regions 17-18.5%; main roles 17-19%).

## Tried inside training, didn't help (2026-10-26)

Player-grouped 5-fold CV on v1's training players only, repeated 3-5 times, LightGBM with
`configs/train.yaml` and inner early stopping. Out-of-fold PR-AUC; the general model scores
0.496-0.500. Ad-hoc scripts, not kept. Internal notes: not for the model card or the site.

- **Separate models** per tier (0.482), region (0.463) or main role (0.464): worse than the
  general model in every tier, region and role. Each loses data, and the signals are shared.
- **Inputs:** region (no change), main role (-0.004), KDA, deaths and win rate relative to the
  role's average (no change), four blends (activity trend 7d vs 8w and 2w vs the 2 before,
  hours idle vs the usual gap, recent losses x idle week): -0.003 (95% CI -0.007 to +0.001).
- **Tier as an input:** +0.007 PR-AUC and better log loss, mostly in Diamond. But tier is read
  at collection time, after the outcomes (a Diamond who quits can decay), so it is a leak until
  rank is recorded at each cutoff.
- **Bronze learning curve:** Bronze-only 0.531 to 0.551 (136 to 547 examples, +0.012 per
  doubling); the general model 0.570 to 0.601 on the same players; recency 0.549. It motivates
  ADR 0015.
- In Gold, churn barely moves with recent win rate (18-23% across bands).

## Tests

`tests/test_model.py`: the feature-list drift guard, loading, split properties, each model,
Platt scaling, bootstrap, reliability, train and reload end to end, no identifiers in the
outputs, and the CLI. Runs in about 5 seconds.
