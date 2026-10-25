# 0013: Candidate features, judged by the forward test

**Status:** Accepted, 2026-10-25

## Context

- ADR 0010 tried four features that tell a break from quitting. They lifted LightGBM from
  0.464 to 0.476 PR-AUC on the 4a test set, but a 200-churner test can't resolve a gain that
  small, so they were removed, with a note to revisit them when there is more test data.
- A training-only look at social ties found one more candidate. Teammates who were on the
  player's team in at least two of their last 20 games (likely premades) separate churners
  among players idle 7 to 28 days about as well as the best existing feature there (AUC 0.598
  against 0.610), and that group is where every model struggles. Adding the count to
  LightGBM raised out-of-fold PR-AUC by +0.005 to +0.007 on three sets of folds. Other social
  variants (share of games with a premade, whether the last game had one) were mixed and
  were dropped. None of this read the test set.
- The forward test (ADR 0011) has about 650 churners on outcomes nobody has seen. Two
  LightGBMs that share 21 features make a paired comparison with a far narrower interval
  than a comparison with the recency rule.

## Decision

**Five candidates**, computed in `src/lolret/dataset/candidates.sql` under the timing rules of
ADR 0006 and written to `candidates.parquet` by `lolret build`:

| Feature | Meaning |
|---|---|
| `returns_8w` | Times in the 8 weeks before T that games came back after a week without any |
| `longest_gap_days` | The longest gap between two consecutive recent games |
| `break_vs_longest_gap` | Days since the last game divided by `longest_gap_days` (floored at an hour) |
| `summoner_level` | Account level at the most recent game, a stand-in for account age |
| `repeated_teammates` | Teammates on the player's team in at least two of the 20 recent games |

The leak guard covers them. Two injected leaks, teammates from a game ending a day after T and
a week of activity past T, each failed it on all 5 seeds. Extraction now keeps each match's
summoner level and the teammates' PUUIDs, which stay under `data/` like every identifier.

**Model.** LightGBM on the 21 features plus the 5 candidates, with the ladder's protocol and
parameters (ADR 0008). The candidates stay out of `FEATURES`: the ladder, the nets and the
model card keep the 21 features until the forward test decides.

**The rule, set before the candidate model was trained on real data:**

1. The candidates join the feature list if, on the forward test, LightGBM with them beats the
   frozen LightGBM: the paired 95% bootstrap interval of the PR-AUC difference is above zero.
   Otherwise they stay out, and this ADR records the result.
2. The comparison on the 4a test set (`lolret train-candidates`) is reported but decides
   nothing: that test set already judged four of these features.
3. The entry is frozen as `candidates` in `configs/forward.yaml`, after the ladder's hash and
   before any label is collected.

## Result on the 4a test set (for the record, rule 2)

LightGBM with the candidates scored 0.458 PR-AUC (ROC-AUC 0.826) against 0.464 (0.825) for
the ladder's LightGBM: a difference of -0.006 (95% CI -0.032 to +0.019). No sign of a gain
there, which, with this test set's noise, says little either way. The forward test decides.

## Consequences

- New `candidates` table and file, `lolret train-candidates`, and
  `lolret forward predict-candidates`. The `matches` table gains two columns.
- The forward test now answers three questions: LightGBM against the recency rule (the one set
  first, ADR 0011), the nets against LightGBM (ADR 0012) and the candidates against LightGBM.
  Each is reported with its own interval; the first stays the headline.
