# 0006: Eligible population and what each feature may read

**Status:** Accepted, 2026-10-22

## Context

The pilot (ADR 0005) showed that about a quarter of player-cutoff pairs had not played at all
in the weeks before the cutoff. Asking "will this player stop playing?" about someone who has
already stopped is trivial: in the pilot, 12 of the 16 such pairs were labelled churned. Keeping
them would inflate every metric without the model learning anything useful.

A tempting alternative is to keep only players who are active *now*. That selects players on
their future: anyone who quit after a cutoff disappears from the sample. In the pilot, filtering
on "played in the last two weeks" made churn at the earlier cutoffs look like 12% instead of
21%. It is the same class of mistake as the 2024 leak (ADR 0003), so it is ruled out.

## Decision

**Eligibility is decided at each cutoff, using only the past.** A (player, cutoff T) pair is
eligible if the player started at least one game, in any queue, in the 28 days before T. The
question the model answers is therefore: *this person played in the last 4 weeks; will they
play at all in the next 4?*

Ineligible pairs stay in the dataset with `eligible = false`, for analysis. Models train and
evaluate on eligible pairs only.

**Timing rules for every column** (enforced in `src/lolret/dataset/features.sql`):

| Part | May read |
|---|---|
| Activity counts | Time buckets that end at or before T. A game counts in the bucket where it *started*, so a game in progress at T is known to exist. |
| Match features | Only games that *ended* at or before T. A game still running at T has no result yet. |
| Label | Only buckets inside (T, T + 28 days]. NULL if that window isn't fully covered by data. |
| Never | `league-v4` wins, losses, LP or flags (measured at collection time, after T). Tier and division are kept as metadata for stratifying, not as features. |

`tests/test_dataset.py` holds the leak guard: on random data, features computed from the full
history must equal features computed after deleting everything after each cutoff. It was
checked by injecting two leaks (one day of match data past T; one week of activity past T);
both made it fail.

## Consequences

- At the pilot's rates, about 64% of pairs are eligible and churn among them is about 21%.
  For the full run that is roughly 11-12k eligible examples.
- Everything needed to apply the rule is already collected, so the run's data does not change.
- **Forward test (added to the roadmap):** once a model exists, predict for every eligible
  player at a cutoff of "today", collect again 28 days later, and compare. That is a test on
  outcomes that had not happened when the model made its predictions. It reuses cached data,
  so only the new weeks are requested.
