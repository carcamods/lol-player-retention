# Dataset and features

`lolret build` turns a collection run into one row per (player, cutoff T): the table `examples`
in `data/processed/<run>/dataset.duckdb`, also written as `examples.parquet`. All definitions
live in [`src/lolret/dataset/features.sql`](../src/lolret/dataset/features.sql). Timing rules and
the eligibility rule are in [ADR 0006](decisions/0006-eligible-population.md).

## Keys and metadata

| Column | Meaning |
|---|---|
| `platform`, `puuid` | The player. `puuid` never leaves the machine (exports use salted hashes). |
| `tier`, `division` | Ladder position at **collection time**. Metadata for stratifying, not a feature. |
| `cutoff` | T, naive UTC midnight. |

## Label and eligibility

| Column | Definition |
|---|---|
| `eligible` | Started at least one game, any queue, in the 28 days before T. |
| `churned` | Started no game at all in (T, T + 28 days]. NULL if that window isn't fully observed. |

## Activity features (from weekly game counts, any queue)

| Column | Definition |
|---|---|
| `games_0_7d` | Games started in the 7 days before T. |
| `games_8_14d` | Games started 8–14 days before T. |
| `games_15_28d` | Games started 15–28 days before T. |
| `games_29_56d` | Games started 29–56 days before T. |
| `active_weeks_8w` | Number of the 8 weeks before T with at least one game. |

## Match features (from the 20 most recent games that ended before T)

| Column | Definition |
|---|---|
| `recent_games` | How many games the features below are based on (up to 20). |
| `days_since_last_game` | Days from the end of the most recent game to T. The recency baseline. |
| `win_rate`, `win_rate_last5` | Share of wins, over all recent games and over the last 5. |
| `loss_streak` | Losses in a row up to the most recent game. |
| `kda` | Mean of (kills + assists) / max(deaths, 1). |
| `deaths_avg` | Mean deaths per game. |
| `duration_min_avg` | Mean game length in minutes. |
| `remake_share` | Share of games ended by an early-surrender vote (remakes). |
| `surrendered_loss_share` | Share of games lost by surrender. |
| `ranked_share`, `aram_share` | Share of games in ranked (Solo/Duo, Flex) and in ARAM. |
| `champion_diversity` | Distinct champions / games. |
| `main_role_share` | Share of the most-played role among games with a role (Summoner's Rift). |
| `gap_hours_median` | Median hours between one game's end and the next game's start. |
| `last_session_games` | Games in the most recent session (a session ends after a break of more than an hour). |

Missing values are deliberate: a player whose only recent game was still running at T has
activity counts but no match features. LightGBM handles them natively; logistic regression
imputes the training median and adds a missing-value indicator (ADR 0008).

## Candidate features (not model inputs yet)

`candidates.parquet` (`src/lolret/dataset/candidates.sql`) has one row per (player, cutoff)
with five candidates that the forward test judges before they join the model (ADR 0013).
Same timing rules as above.

| Column | Definition |
|---|---|
| `returns_8w` | Times in the 8 weeks before T that games came back after a week without any. |
| `longest_gap_days` | The longest gap between two consecutive recent games, in days. |
| `break_vs_longest_gap` | Days since the last game divided by `longest_gap_days` (floored at an hour). |
| `summoner_level` | Account level at the most recent game, a stand-in for account age. |
| `repeated_teammates` | Teammates on the player's team in at least two of the 20 recent games (likely premades). |

## Match sequences (for the neural nets)

`sequences.parquet` has one row per (player, cutoff, game) for the same 20 most recent games
that ended before T, `rn` = 1 being the most recent (`src/lolret/dataset/sequences.sql`). The
GRU reads them oldest first (ADR 0012).

| Column | Definition |
|---|---|
| `rn` | Position, 1 = the most recent game before T. |
| `hours_before_cutoff` | Hours from the game's end to T. |
| `gap_hours` | Hours from the previous game's end to this game's start; NULL for the oldest game in view. |
| `duration_min` | Game length in minutes. |
| `win`, `kills`, `deaths`, `assists` | The player's result and score. |
| `remake`, `surrendered` | Ended by an early-surrender vote; ended by any surrender. |
| `queue_id`, `team_position` | Queue (420 Solo/Duo, 440 Flex, 450 ARAM...) and role, NULL off Summoner's Rift. |
| `same_champion` | Same champion as the previous game; NULL for the oldest game in view. |
