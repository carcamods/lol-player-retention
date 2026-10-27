# 0015: Bronze expansion, judged by a rule set before collecting

**Status:** Accepted, 2026-10-26. Result, 2026-10-27: the rule was not met, so the general
model stays (one model for every tier).

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

## Result (2026-10-27)

The run finished with all 5,568 Bronze players (4,704 new) and 0 open failures; `lolret build`
gave 9,081 eligible examples, 23.9% churned. `lolret train-bronze -c configs/train.yaml` applied
the rule as written (`src/lolret/model/bronze.py`; numbers in `data/models/bronze/evaluation.json`).

- **Data.** The general model trained on 9,249 examples from 5,487 players (20.4% churned), the
  Bronze-only model on their Bronze rows: 4,316 examples from 2,635 players (24.4%). Fresh
  Bronze test players: 750, of whom 179 churned (estimated beforehand: about 700 and 180).
- **Rule 1 not met: the general model stays.** Bronze-only PR-AUC 0.570, general 0.566: +0.004
  (95% CI -0.033 to +0.037). ROC-AUC 0.837 against 0.838 and Brier 0.133 for both: on Bronze
  the two models are the same.
- **Rule 2 not met: the general model doesn't beat the recency rule.** PR-AUC 0.566 against
  0.538: +0.028 (95% CI -0.021 to +0.084). The other metrics favour the model more clearly
  (ROC-AUC 0.838 against 0.791, Brier 0.133 against 0.146), but the rule is PR-AUC's interval,
  and it includes zero.

Reported, not decided on:

- **EUW alone** (235 players, 60 churned): Bronze-only against general -0.016 (95% CI -0.070
  to +0.027); general against the recency rule +0.009 (-0.063 to +0.091). Nothing points to a
  gain specific to EUW.
- **Learning curve.** Bronze-only on shares of the Bronze training players, on the same test
  players (below the full set, the mean of 3 random subsets): 272 examples 0.518, 538 0.538,
  1,075 0.540, 2,158 0.558, 4,316 0.570. About +0.013 per doubling, as v1's curve suggested
  (+0.012). With 8 times v1's Bronze data the Bronze-only model reaches the general model, which
  learned from the same Bronze rows plus every other tier, but doesn't pass it.
- **v1's players in both runs.** The 646 v1 Bronze players with labelled rows have the same
  labels in both builds. Two features differ: `kda` by float rounding (9 rows) and
  `gap_hours_median` (by up to 1.7 hours in 48 rows of 39 players, 36 of those rows among the
  eligible, labelled ones that are modelled). The Bronze store holds extra
  match details for 68 of these players, fetched for new players in the same games, and the
  oldest of the 20 recent games gets a gap only when the game before it is cached. Those games
  ended before the cutoff, so it isn't a leak, but the feature depends slightly on what else was
  collected. Every test player's rows come from the one build. Noted in
  `src/lolret/dataset/AGENTS.md`.

**What it means.** On Bronze, one model for every tier predicts as well as a model of its own,
even with 4,316 Bronze training examples: the signals are shared across tiers, as the per-tier
models on v1 suggested. The expansion still paid off as test data, with 179 fresh churners
against 33 Bronze churners in the 4a test set. It also gave the model's largest lead over the
recency rule so far, though still not one that clears the rule. The headline model and the forward test
(ADR 0011) are unchanged. The EUW-focused expansion was the next step only if Bronze-only won,
so it drops out of milestone M5.

## Consequences

- `CollectConfig` gains `base_run`, and `LayeredStore` moves from `lolret.forward.collect` to
  `lolret.collect.store`, so collection runs and the forward test share it. `lolret collect`,
  `status` and `build` open a run with its base.
- `data/raw/bronze.sqlite` (about 1.5 GB) and `data/processed/bronze/`. v1 is not modified.
- If Bronze-only wins, an EUW-focused expansion is the natural next step, ideally on a
  production key. If not, this ADR records the negative result and the general model stays.
- The forward test (ADR 0011) is independent of this run.
