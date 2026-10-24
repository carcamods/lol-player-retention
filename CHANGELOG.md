# Changelog

Notable changes, newest first. Each entry says what changed and why.

## [2026-10-24] Phase 4a: classical models

### Added
- `lolret train -c configs/train.yaml`: trains a majority-class baseline, the recency rule,
  logistic regression and LightGBM on a built dataset, and evaluates them on held-out players
  at the latest cutoff. Output in `data/models/<dataset>/`: `models.json` and `lightgbm.txt`
  (no pickles), `metrics.json`, `model_card.md` (ADR 0008).
- Model selection (logistic-regression strength, LightGBM rounds) and Platt calibration use
  player-grouped out-of-fold predictions inside training, so the test set is used only once.
- 95% bootstrap intervals for PR-AUC, ROC-AUC, Brier score and log loss, plus a paired interval
  for each model's PR-AUC gain over the recency rule. The model card says plainly whether a
  model beats the baseline.
- Feature importance from LightGBM's built-in TreeSHAP, and reliability bins for the
  calibration plot.
- Tests: the model's feature list must match `features.sql`, split properties, save and reload,
  and a check that no player identifier reaches any output.
- Dependencies: scikit-learn, LightGBM.
- First results on run `v1` (1,104 held-out players, 18% churn): LightGBM PR-AUC 0.464, the
  recency rule 0.455, logistic regression 0.452. No model clearly beats the recency rule; the
  README has the table.

## [2026-10-22] AGENTS.md instead of CLAUDE.md

### Changed
- Context files renamed from `CLAUDE.md` to `AGENTS.md` (root, `docs/`, `tests/`, `riot`,
  `collect`, `dataset`). `AGENTS.md` is the open format most coding agents read, and Claude Code
  reads it whenever no `CLAUDE.md` exists, so one set of files serves every tool (ADR 0009).
- The root map now tells agents to read a module's `AGENTS.md` before changing code there,
  because not every tool loads subfolder files by itself.

### Added
- README section "How this project is built": the AI-assisted workflow and the guards behind it.

## [2026-10-22] Layered repo memory for AI-assisted development

### Added
- Module context files (`CLAUDE.md` in `riot`, `collect`, `dataset`, `tests`, `docs`): purpose,
  status, rules that must not break, pitfalls and tests. They load only when that folder is in
  use, so sessions read what the task needs instead of the whole repo (ADR 0007).
- ADR index (`docs/decisions/README.md`) with a template.
- `/checkpoint` and `/adr` commands for ending a session and recording decisions.
- "Working with AI agents" section in `docs/standards.md`.

### Changed
- Root `CLAUDE.md` rewritten as a short map: "Active work", where things live, rules that
  always apply.

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
