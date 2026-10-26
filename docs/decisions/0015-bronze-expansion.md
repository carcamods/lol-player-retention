# 0015: Bronze expansion, judged by a rule set before collecting

**Status:** Accepted, 2026-10-26. Collection running; the rule below is judged once it is done.

## Context

On run `v1`, a model trained on one tier predicted that tier worse than the general model in
all 7 tiers (cross-validation inside training, 2026-10-26). The owner's view is that a tier
model is starved of data rather than wrong: v1 has 72 players per division, so about 700
training examples per tier.

A learning curve on Bronze (training only) supports trying. A Bronze-only LightGBM went from
0.531 to 0.551 PR-AUC between 136 and 547 training examples, about +0.012 per doubling. The
general model scored 0.570 to 0.601 on the same Bronze players, and the recency rule 0.549. At
that rate the Bronze-only model would need about 16 times the data to catch up, but the curve
is short and the extrapolation is uncertain. Only more data answers it.

Why Bronze: it has the highest churn (27% of eligible examples in training, 18% overall), so
each player collected brings 1.5 times as many churners as average. It is also where the most
players are lost. Today the 4a test set holds only 33 Bronze churners, too few to measure Bronze
at all.

## Decision

**Collect** `configs/collect-bronze.yaml`, run `bronze`: Bronze only, the 3 platforms, 464
players per division instead of 72, with v1's seed, dates and ladder pages.

- The new `base_run: v1` option reads v1's store and never writes it. The sample is
  prefix-consistent (ADR 0005), so its first 72 players per division are v1's. An offline check
  confirmed this in all 12 divisions, with every ladder page served from v1's cache (0 network
  requests). Only the 4,704 new players are requested: about 25 h, platforms in parallel.
- All 3 platforms rather than one: the rate limit is per region, so three collect three times
  faster, and churn is alike across regions (17-18.5%).
- One API key. Riot allows one key per product, so keys from other accounts are not pooled.
  The owner applies for a production key in parallel (`docs/riot-production-key.md`).

**The rule, set before any of the new data is seen.** It is judged on the fresh Bronze test
players: the new players (not in v1) held out by the usual hash (`test_fraction` 0.3, seed 42),
eligible and labelled at 2026-09-24. v1's own Bronze test players are left out, because the 4a
evaluation has already looked at them. Estimated from v1's Bronze rates: about 700 examples and
180 churners.

Two LightGBM models, both with the 21 features and ADR 0008's settings (`configs/train.yaml`:
5 player-grouped folds, early stopping, Platt scaling), trained on the players who are not held
out, at the cutoffs before 2026-09-24:

- **General:** every tier (v1's training players plus the new Bronze players).
- **Bronze-only:** the Bronze rows of the same set.

1. **Bronze-only against general.** Paired bootstrap over players (1,000 resamples), 95%
   interval of the PR-AUC difference. Above zero: Bronze gets its own model. Below zero, or
   overlapping zero: the general model stays, one model for everyone.
2. **The kept model against the recency rule**, on the same players and the same way. It beats
   the rule only if the interval is above zero.

**Reported, not decided on:** the same comparisons on EUW alone (the largest Bronze ladder:
about 593k players, against 512k on KR and 284k on NA, estimated from the cached pages), and the
Bronze learning curve with all the new data.

## Consequences

- `CollectConfig` gains `base_run`, and `LayeredStore` moves from `lolret.forward.collect` to
  `lolret.collect.store`, so collection runs and the forward test share it. `lolret collect`,
  `status` and `build` open a run with its base.
- `data/raw/bronze.sqlite` (about 1.5 GB) and `data/processed/bronze/`. v1 is not modified.
- If Bronze-only wins, an EUW-focused expansion is the natural next step, ideally on a
  production key. If not, this ADR records the negative result and the general model stays.
- The forward test (ADR 0011) is independent of this run.
