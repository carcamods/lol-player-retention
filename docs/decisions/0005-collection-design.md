# 0005: Collection design

**Status:** Accepted, 2026-10-22

## Context

The dataset needs, for each sampled player and each cutoff T: weekly activity before T,
details of the last ~20 matches before T, and whether they played at all in the 28 days after
T. A personal key allows 100 requests per 2 minutes per routing value, so a full run takes
days. It must survive interruptions, never re-request data, and never leak the key.

## Decision

**Sampling.** Players are drawn from the current Ranked Solo/Duo ladder (`league-v4`) on NA1,
EUW1 and KR, Iron to Diamond, stratified by division. For each division, the last page is
found by exponential then binary search, a few random pages are fetched, and players are
drawn from them with a seeded PRNG, so the sample is reproducible.

**Time grid.** Time is cut into 7-day buckets from the earliest cutoff's lookback (56 days)
to the latest cutoff's label window (28 days). Cutoffs are 28 days apart and fall on bucket
boundaries. For each bucket, the player's match IDs come from `match-v5 by-puuid` with
`startTime`/`endTime`. That is usually one request per bucket, and it gives weekly activity
counts and the label without fetching any match details.

**Details.** Full match details are fetched only for the 20 most recent matches before each
cutoff. Matches shared by two cutoffs are fetched once.

**Season.** The ranked year began 2026-01-08. Season 3 (2026-07-29) carried ranks over without
a reset, so the current ladder still contains everyone who played ranked this year. The config
records `season_start` and rejects any range that starts before it. Phase 3 checks the data for
a reset (a spike of ranked games) rather than trusting third-party sources.

**Client.** An async httpx client sends the key in the `X-Riot-Token` header, never in the URL
(the 2024 version put it in query strings). It keeps one sliding-window rate limiter per
routing value, so a platform (`na1`) and its region (`americas`) use their separate budgets, and
platforms run in parallel. 429s honour `Retry-After`; 5xx and network errors back off and
retry; 401/403 stop the whole run.

**Storage.** One SQLite file per run (`data/raw/<run_name>.sqlite`, WAL mode). It holds every
200 and 404 response keyed by routing + path + sorted query, the open failures, and the
sampled players with their completion state. SQLite rather than DuckDB because this is a
long, write-heavy job: each response is committed as it arrives, and `lolret status` can read
the file while `collect` writes to it. DuckDB stays the plan for Phase 3 analytics.

**Failure policy.** A player whose requests still fail after retries is logged, left
incomplete, and retried on the next run. The run exits with code 2, so nothing fails silently.
A rejected key exits with code 1. Ctrl+C exits with 130. Progress is never lost.

## Consequences

- Re-running the same config is always safe and only fetches what is missing.
- About 20 match-ID requests plus up to 60 detail requests per player. The pilot run
  (`configs/collect-pilot.yaml`) measures the real average before the full run.
- Matches are bucketed by **start** time. A game that starts just before T ends after it, so
  Phase 3 must use only matches that *ended* before T for features.
- Ladder data is "now" data: `league-v4` fields other than the PUUID are never used as
  features (ADR 0003).
- Bodies are stored zlib-compressed (a match is ~80 KB raw, ~11 KB compressed).
- Sampling shuffles each division's pool once and takes the first N, so raising
  `players_per_division` later keeps every sampled player and only adds new ones.

## Pilot results (2026-10-22)

`configs/collect-pilot.yaml`: 15 NA players (Silver II, Gold II, Emerald II), 3 cutoffs.

| Measure | Result |
|---|---|
| Outcome | 15/15 players complete, 0 failures, 0 rate-limit errors |
| Requests | 768 in 14 min: the 100-per-2-minutes limit is the bottleneck, as designed |
| Per player | 20 match-ID + 27.4 match-detail requests = 47.4 |
| Per division (ladder) | ~19 requests with 2 pages; ~23 with 6 |
| Storage | ~11 KB per match compressed |
| Churned at the cutoffs | 6/15, 5/15, 7/15 (about 40%) |
| No game in the 8 weeks before the cutoff | 12 of 45 player-cutoff pairs |

**Full run estimate** (`configs/collect.yaml`, 2,016 players per platform): ~650 ladder requests
(~13 min) then ~95,600 match requests (~32 h) per platform. The three platforms run in
parallel, so about **32 hours** in total, and about **2 GB** of disk.

**For Phase 3:** about a quarter of player-cutoff pairs were already inactive before the cutoff.
Predicting churn for someone who has already stopped is trivial and inflates metrics, so
Phase 3 must decide the eligible population (for example, at least one game in the 28 days
before T). At the pilot's rate that leaves roughly 13k of the ~18k examples. If that proves too
few, raise `players_per_division` and re-run: only new players are fetched.
