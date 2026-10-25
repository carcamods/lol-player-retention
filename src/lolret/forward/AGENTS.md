# `lolret.forward`: the forward test (Phase 4c)

Predicts for every eligible player at a cutoff after run `v1`'s last label window, freezes the
predictions by hash, and scores them once the 28-day outcome window has happened. Design and
the question set before freezing: ADR 0011. Config: `configs/forward.yaml`.

**Status:** started 2026-10-25 (cutoff 2026-10-22). Labels can be collected after 2026-11-19
00:00 UTC, then scored.

## Files

- `config.py`: `ForwardConfig` (YAML) and `Forward`, which derives a one-cutoff
  `CollectConfig` from the base run and splits its buckets into feature and label buckets.
  Validates that the cutoff is on the base run's bucket grid and after its last label window.
- `collect.py`: `LayeredStore` (reads through to earlier stores, writes only its own),
  `collect_features` and `collect_labels`, one store per phase.
- `predict.py`: `freeze_predictions` (features at the cutoff, ladder trained on every labelled
  base example, `entries/ladder.csv`, models, `manifest.json`), entry reading and hash checks.
- `score.py`: `score_forward` (checks, labels, `evaluate`, `results.json`, `report.md`);
  later entries are also compared with LightGBM.
- The neural nets' entry lives in `src/lolret/nn/forward.py` (`lolret forward predict-nn`).
- `candidates.py`: `freeze_candidates_entry`, the candidate features' later entry
  (`lolret forward predict-candidates`, ADR 0013).

## Rules that must not break

- **Order.** Features, then predict, then commit the hash in `configs/forward.yaml`, then
  labels, then score. Each step checks the previous one (table in ADR 0011). Never delete the
  labels store or edit an entry file to get around a check.
- **Frozen means frozen.** `predict` never overwrites an entry. A new model joins as a new
  entry with its own hash, before the labels collection starts.
- The base run's store is opened read-only. New responses go to the phase's own store.
- Only weekly buckets that have fully ended are requested: a partial week would be cached as
  final and poison the label.
- Entry files hold PUUIDs and stay under `data/`. Only hashes and aggregate results leave it.

## Tests

`tests/test_forward.py`: config validation, `LayeredStore`, the whole sequence against a fake
Riot API (the base run's cache is reused, its store is untouched, only label buckets are
requested for frozen players, the right players churn), a tampered entry, and each refusal.
