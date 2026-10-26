# `lolret.collect`: sampling and match history

Samples ranked players from the ladder, then fetches each player's match IDs per time bucket
and details for the most recent matches before each cutoff. Everything is cached in one SQLite
file per run, so a run can stop and resume without repeating a request.

**Status:** done (Phase 2). Run `v1` (`configs/collect.yaml`) finished 2026-10-24. The forward
test (`src/lolret/forward/`) and run `bronze` (`configs/collect-bronze.yaml`, ADR 0015) reuse its
store read-only. Pilot results and the full-run estimate are in ADR 0005.

## Files

- `config.py`: `CollectConfig` from YAML. Derives `cutoffs`, `range_start/end` and weekly
  `buckets`, and validates them (multiples of `bucket_days`, range after `season_start`).
  `base_run` names an earlier run whose store is also read, never written.
- `ladder.py`: per division, finds the last page by exponential then binary search, fetches
  random pages, shuffles once with a seed, and takes the first N.
- `history.py`: `bucket_match_ids` (paginated, half-open windows) and `collect_player`.
- `cache.py`: `cache_key` and `CachedRiot`, which answers from the store first.
- `store.py`: SQLite schema (responses, failures, players), zlib-compressed bodies,
  `decode_body` (also reads older plain-text bodies), and read-only mode for `status`.
  `LayeredStore` also answers from earlier runs' stores; the CLI's `run_store` opens a run with
  its `base_run` this way.
- `runner.py`: platforms concurrently (`per_platform`), players sequentially
  (`collect_players`, also used by the forward test); progress logs; `RunResult`.

## Rules that must not break

- **Cache keys stay stable.** Changing how keys are built, or a run config's dates or bucket
  size, means the existing data no longer matches. Never edit `configs/collect.yaml` while a
  run is going; start a new `run_name` instead.
- **Sampling is prefix-consistent:** shuffle once, take the first N. Don't switch to
  `rng.sample`, or raising `players_per_division` would replace players instead of adding them.
- A run with `base_run` keeps the base run's seed, dates, buckets and `pages_per_division`, or
  the base's cache no longer matches and its players aren't reused.
- Every 200 and 404 is stored; failures are recorded and retried on the next run.
  Exit codes: 0 done, 1 key rejected, 2 some failures remain, 130 interrupted.
- Ladder fields other than `puuid` are measured now, after every cutoff: never features.
- The Discord ping only logs the error type, never the webhook URL.

## Tests

`test_collect_config.py`, `test_store.py`, `test_history.py`, `test_collect_run.py` (an
end-to-end run against a fake Riot API: resume, top-up, failed-player retry, rejected key) and
`test_cli_collect.py`. Real-API checks happen only through pilot runs, never in tests.

Related: ADR 0003, ADR 0005.
