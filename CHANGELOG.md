# Changelog

Notable changes, newest first. Each entry says what changed and why.

## [2026-10-22] Phase 3: point-in-time dataset

### Added
- `lolret build`: extracts players, weekly game counts and per-match rows from a run's store
  (never the API; only finished players), then builds one example per (player, cutoff) in
  DuckDB SQL. Output: `data/processed/<run>/dataset.duckdb` and `examples.parquet`.
- 21 features (activity windows, recency, win rate, loss streak, KDA, remakes, surrenders,
  queue mix, champion and role diversity, session gaps), documented in `docs/features.md`.
- Eligibility rule (ADR 0006): a pair counts only if the player played in the 28 days before
  the cutoff. Filtering on activity *now* was rejected because it selects players on their future.
- Leak guard test: features from the full data must equal features from data truncated at
  each cutoff, on random data. Verified by injecting two leaks; both were caught.
- Forward test added to the roadmap (phase 4c).

## [2026-10-22] Phase 2: data collection

### Added
- `lolret collect`: samples ranked players from random ladder pages per division, then fetches
  match IDs per 7-day bucket and details for the 20 most recent matches before each cutoff
  (ADR 0005).
- Async Riot client: key in the `X-Riot-Token` header (2024 put it in URLs), one rate limiter
  per routing value, `Retry-After` on 429, backoff on 5xx and network errors, and a hard stop
  on 401/403.
- SQLite run store: every response is cached, so a stopped run resumes without repeating a
  request. `lolret status` reads it while a run is in progress.
- Optional Discord ping when a run ends. Failures to notify never log the webhook URL.
- Run configs: `configs/collect.yaml` (full) and `configs/collect-pilot.yaml` (cost check).
- `scripts/make_fixtures.py`: builds anonymised test fixtures from a run, refusing to write if
  any real identifier survives.
- `RIOT_RATE_LIMITS` setting, for when a production key raises the limits.
- Response bodies stored zlib-compressed: the pilot showed ~80 KB per match, which would have
  meant ~13 GB for the full run; now ~2 GB.
- Raising `players_per_division` tops up a run instead of being ignored.
- Anonymised fixtures recorded from the pilot run, plus contract tests on the response fields
  the dataset needs. Pilot results are in ADR 0005.

## [2026-10-22]

### Added
- Project foundation: `lolret` package with typed settings (secrets as `SecretStr`), the
  project logging format, and a CLI with `version` and `config` commands.
- Tooling: uv, ruff, mypy (strict), pytest, and pre-commit with gitleaks, large-file and
  notebook-output checks. The 2024 version leaked credentials and committed 40 MB CSVs;
  these hooks block both.
- CI on GitHub Actions: lint, types and tests on Python 3.12 (Colab) and 3.13, plus a
  full-history gitleaks scan.
- Docs: requirements, engineering standards, and ADRs 0001–0004 (fresh repo, static snapshot
  site, point-in-time labels, neural nets on Colab).
- `docs/riot-api-registration.md`: Riot key types and the personal-key application text,
  kept for reuse in a later production-key application.
