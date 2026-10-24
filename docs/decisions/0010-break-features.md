# 0010: Break features, kept only if they pass a rule set in advance

**Status:** Accepted, 2026-10-24

## Context

No classical model clearly beats the recency rule on run `v1` (ADR 0008, README). The EDA
(`notebooks/eda.ipynb`) shows why. 69% of churners hadn't played for 7 to 28 days at the
cutoff, and inside those groups no feature reaches an AUC above 0.60. In-game statistics carry
almost no signal anywhere. What's missing is anything that tells a break from quitting.

The choice was between a short round of targeted features and going straight to the neural
nets (Phase 4b). The GRU would read the same last ~20 matches, whose in-game statistics carry
almost no signal. So if timing features built from that data don't help, a GRU probably won't
either, and if they do, the neural nets get them as inputs.

## Decision

Add four features, all computed only from data we already have, under the existing timing
rules (ADR 0006):

| Feature | From | Meaning |
|---|---|---|
| `returns_8w` | weekly buckets | Times in the 8 weeks before T that games came back after a week without any |
| `longest_gap_days` | recent games | The longest gap between two consecutive recent games |
| `break_vs_longest_gap` | recent games | Days since the last game divided by `longest_gap_days` (floored at an hour) |
| `summoner_level` | recent games | Account level at the most recent game, a stand-in for account age |

Activity over a window longer than 8 weeks was considered and left out: the earliest cutoff
has only 8 weeks of history, so it would need a new collection run.

**The rule, set before any result was seen.** The features stay if either holds on the test
set:

1. LightGBM with them beats the recency rule: the paired 95% bootstrap interval of the PR-AUC
   difference excludes zero.
2. Among test examples whose last game was 7 to 28 days before the cutoff, LightGBM with them
   beats LightGBM without them: the paired 95% bootstrap interval of the PR-AUC difference
   excludes zero.

Otherwise they are removed, this ADR records the negative result, and work moves to Phase 4b.

## Consequences

- The dataset gains a column (`summoner_level`) in the matches table, read from the stored
  match details, so no new API calls are needed.
- The model's feature list grows from 21 to 25. Model files saved with the old list refuse to
  load, which is intended.
- Writing the rule down before training keeps the decision honest. The alternative, trying
  features until one helps, would overfit the test set.
