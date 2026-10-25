# `lolret.export`: the anonymised snapshot for the site (FR4)

`lolret export` writes `data/snapshot/<dataset>/snapshot.json`: the held-out test players at
the latest cutoff, numbered by a throwaway salt, with probabilities, outcomes, drivers and
weekly activity. Design: ADR 0014 (and ADR 0002 for why the site is a snapshot).

**Status:** done (2026-10-25). Published: the owner chose to show the weekly timeline as is
(ADR 0014), and `site/data/snapshot.json` is a committed copy of the `v1` export.

## Files

- `demo.py`: a random snapshot with the real structure, for building the site in CI
  (`python -m lolret.export.demo`).
- `snapshot.py`: `anonymous_ids` (salted-hash order → "Player 0001"...), `forward_summary`
  (the forward test's status, hashes and, once scored, its aggregate results), `export_snapshot`.

## Rules that must not break

- **Nothing identifying leaves `data/`.** No PUUID, Riot ID, match ID or salt in the output.
  The salt is drawn per export and never stored or logged.
- Only held-out test players: never training players, whose predictions would look better than
  the model is.
- Days since the last game is rounded to a tenth of a day (`DECIMALS`). Finer, it pins the
  time of a player's last game, which identifies more than the weekly counts.
- The export writes under `data/`. Publishing is a deliberate, separate step: copy it into
  `site/data/`, check the diff, commit.

## Tests

`tests/test_export.py`: every held-out player and no identifier in the output, days since the
last game rounded, numbering that depends only on the salt, the timeline against the buckets,
and the CLI without models.
