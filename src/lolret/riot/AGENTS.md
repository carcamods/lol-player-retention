# `lolret.riot`: Riot API client

A thin async client: routing, rate limiting, retries and typed errors. It knows nothing about
collection runs or storage.

**Status:** stable since Phase 2. Changes here are rare and affect every run.

## Files

- `routing.py`: platform (`na1`) → regional cluster (`americas`) map, the account-v1 cluster
  (`account_region_for`: SEA accounts live under `asia`), and base URLs.
- `ratelimit.py`: `RateLimiter`, a sliding log per window; `parse_limits("20:1,100:120")`.
- `client.py`: `RiotEndpoints` (league entries, match IDs, match, and account by Riot ID for
  `lolret predict`, on top of an abstract `get`) and
  `RiotClient` (the network implementation). Errors: `RiotAuthError`, `RiotRequestError`.

## Rules that must not break

- The key goes only in the `X-Riot-Token` header. It never appears in a URL, log line or error.
- One `RateLimiter` per routing value: Riot's limits are per routing value, which is what lets
  regions run in parallel.
- 401/403 raise `RiotAuthError` and stop the run (retrying can't fix a bad key). 404 is a normal
  answer and is returned. 429 waits for `Retry-After`; 5xx and network errors back off.
- **Endpoint paths and parameters are cache keys.** `CachedRiot` (collection) and `StoredOnly`
  (dataset) both subclass `RiotEndpoints`, and the store is keyed by routing + path + sorted
  params. Changing a path or a parameter name or value orphans every existing run's data.

## Riot facts worth knowing

- Personal and development keys: 20 requests per second and 100 per 2 minutes, per routing value.
- `summonerId` is gone from `league-v4`; everything is keyed by `puuid`.
- `match-v5` returns at most 100 match IDs per call; `endTime` is inclusive.

## Tests

`tests/test_client.py` (respx: header auth, 404, 401/403, 429, 5xx, network errors) and
`tests/test_ratelimit.py` (fake clock, so no real waiting).

Related: ADR 0005.
