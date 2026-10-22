# 0003: Point-in-time features and labels

**Status:** Accepted, 2026-10-22

## Context: the 2024 leak

The 2024 version reported 91% test accuracy and 89% on a holdout. Those numbers were not
real:

- Each player's matches were bucketed into `initial` / `mid` / `late` using **global**
  date quantiles across all players, not per player.
- The label was "days since the player's last game, relative to the dataset's newest
  game" (≤ 28 days → active).
- Inactive players, by definition, had no games in the newest third of the date range.
  Their `*_late` features were all missing and filled with 0.
- The model learned "has late-segment games", which is the label itself. That's why every
  top feature ended in `_late`, and why accuracy jumped from 55% (one honest feature) to 91%.
- The validation set also re-computed its own quantiles and normalisation.

## Decision

- Each example is a (player, cutoff T) pair.
- **Label:** `churned` = the player plays no game of any queue in (T, T + 28 days].
  Label windows are always fully in the past.
- **Features:** computed by functions that take `as_of=T` and only read data at or before T.
- **Never** use `league-v4` wins, losses, LP, `inactive` or `hotStreak` as features. They
  are measured at collection time, after T.
- A leak-guard test injects post-T matches and asserts that no feature changes.
- Validation is temporal and player-grouped: train on earlier cutoffs, test on the latest,
  with no player in both.
- Natural class balance; no 500/500 resampling.
- Every model must be reported next to the recency baseline ("days since last game").

## Consequences

- Reported metrics will be lower than 2024's, and honest. Beating the recency baseline is the
  real bar.
- The model card tells the leak story openly; it demonstrates the skill of catching one.
