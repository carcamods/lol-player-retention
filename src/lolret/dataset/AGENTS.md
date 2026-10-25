# `lolret.dataset`: point-in-time examples

Turns a run's store into one row per (player, cutoff T): features, `eligible` and `churned`.
Reads only stored responses, never the API, and only players whose collection finished.

**Status:** done (Phase 3), built on run `v1` (6,048 players, 11,678 eligible examples) and
explored in `notebooks/eda.ipynb`.

## Files

- `extract.py`: `StoredOnly` (a `RiotEndpoints` that reads the store, so keys match collection
  exactly), `participant_row`, and the `players`, `buckets` and `matches` tables (naive UTC).
  `until` skips buckets that end later (the forward test, before its labels exist).
- `features.sql`: every feature and the label, in one DuckDB query. **The definitions live
  here**, documented column by column in `docs/features.md`.
- `sequences.sql`: the 20 most recent finished games per (player, cutoff), one row each, for
  the neural nets (ADR 0012). Same timing rule as the match features.
- `candidates.sql`: five candidate features per (player, cutoff), kept apart from
  `features.sql` until the forward test decides (ADR 0013).
- `build.py`: `build_examples` (tables → `examples` in a DuckDB connection) and
  `build_dataset` → `data/processed/<run>/dataset.duckdb` + `examples.parquet`, rebuilt from
  scratch every time, plus `sequences.parquet` and `candidates.parquet`.

## Rules that must not break (ADR 0003, ADR 0006)

| Part | May read |
|---|---|
| Activity counts | buckets that end at or before T (games counted by start time) |
| Match features | games that ended at or before T |
| Label | only (T, T + 28 days]; NULL if not fully observed |
| Eligibility | at least one game in the 28 days before T |
| Never | ladder fields (wins, losses, LP, flags) as features |

## Adding or changing a feature

1. Change `features.sql`, keeping the timing rules above.
2. Add the column to `docs/features.md`.
3. Extend the hand-built scenario in `tests/test_dataset.py` with its expected value.
4. Run the leak guard, then prove it still bites: temporarily make the new feature read past T
   and check the test fails.

Before training with a new feature, write down the result that keeps it, and record the outcome
either way (ADR 0010: four break features were tried this way and removed).

NULLs are deliberate (for example, no match features when the only recent game was still
running at T). Imputation belongs to modelling, not here.

## Tests

`tests/test_dataset.py`: the scenario tests (features, sequences, candidates), the leak-guard
property tests for each of the three (random data, 5 seeds, 3 cutoffs), extraction from a
store, and the build outputs.
