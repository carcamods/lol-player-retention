# `lolret.export`: the anonymised snapshot for the site (FR4)

`lolret export` writes `data/snapshot/<dataset>/snapshot.json`: the held-out test players at
the latest cutoff, numbered by a throwaway salt, with probabilities, outcomes, drivers and
weekly activity. Design: ADR 0014 (and ADR 0002 for why the site is a snapshot).

**Status:** done (2026-10-25). Not published: the owner decides first how much of the weekly
timeline to show (ADR 0014).

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
- The export writes under `data/`. Publishing (copying into the site) is a deliberate,
  separate step, after the ADR 0014 question is settled.

## Tests

`tests/test_export.py`: every held-out player and no identifier in the output, numbering that
depends only on the salt, the timeline against the buckets, and the CLI without models.
