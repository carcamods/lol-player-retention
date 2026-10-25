# 0014: Snapshot export: held-out players, numbered by a throwaway salt

**Status:** Accepted, 2026-10-25. Published with the weekly timeline as is (owner's decision,
2026-10-25, below).

## Context

The public site serves a frozen, anonymised snapshot and never calls the API (ADR 0002,
FR4, FR5). It needs, per player, a churn probability, the actual outcome, the top drivers and
an activity timeline, plus the model's headline metrics.

## Decision

- **Who:** the held-out test players at the latest cutoff (1,104 on run `v1`). The model never
  saw them, so each prediction can be shown next to what actually happened without flattering
  the model.
- **What:** region, tier and division (collected at sampling time, metadata only, never
  features), the calibrated LightGBM probability, the recency rule's, the outcome, games in
  the last 28 days, days since the last game, recent win rate, the three biggest SHAP drivers,
  and games per week from 8 weeks before the cutoff to 4 after. Also the test metrics of every
  model in the model card.
- **Identifiers:** players are numbered "Player 0001"... in the order of a salted SHA-256 of
  their PUUID. The salt is random for every export and never stored, so the numbers can't be
  traced back and change between exports. No PUUID, Riot ID or match ID is written; a test
  checks the output for the synthetic PUUIDs, and the `v1` export was checked against all
  6,048 real ones.
- **Where:** `lolret export` writes `data/snapshot/<dataset>/snapshot.json`, under `data/`, so
  nothing is published by running it. Copying it into the site is a separate step.

## Publishing: the weekly timeline as is (owner, 2026-10-25)

The weekly timeline plus region and tier is the most identifying part the site needs: someone
determined could compare a player's week-by-week game counts with public match-history sites
and find the account. The options were to publish it as is (FR5 asks for a timeline), coarsen
the counts (for example 0, 1-5, 6-15, 16+), or show only the 8 weeks before the cutoff.

**Decision:** publish it as is. The games are already public on every match-history site, the
snapshot names no one, and coarse counts would hide the pattern the Explorer is there to show:
activity fading before a player stops.

**Coarsened anyway:** days since the last game, rounded to a tenth of a day (about 2.4 hours).
At three decimals it pinned a player's last game to about 90 seconds, which identifies far
more than the weekly counts and tells a reader nothing more.

## Consequences

- New module `src/lolret/export/` and command `lolret export` (after `lolret train`).
- The snapshot is 0.7 MB of JSON for 1,104 players, small enough for a static site.
- When the forward test is scored, its players can be exported the same way.
- `site/data/snapshot.json` is committed. Each export draws a new salt, so player numbers
  change whenever the snapshot is refreshed, and git keeps every published version.
