# Changelog

Notable changes, newest first. Each entry says what changed and why.

## [2026-10-26] The site is live

### Added
- The site's link in the README: the top, the 30-second summary and "The site". It is live at
  carcamods.github.io/lol-player-retention, deployed by hand with `pages.yml` from the
  committed v1 snapshot.

### Changed
- The repo is public. A ruleset on `main` requires a PR and the three CI checks (both Python
  versions and the gitleaks scan) to merge, blocks force pushes and deletions, and has no
  bypass. It needs no approval, since GitHub doesn't let an owner approve their own PR.
- Milestone M1 (go public) is done; the checklist and roadmap are ticked.

## [2026-10-26] Bronze expansion

### Added
- `configs/collect-bronze.yaml` (run `bronze`, ADR 0015): Bronze only, 464 players per division
  instead of 72, on the 3 platforms. It tests whether a Bronze-only model wins once it has
  enough data, by a rule written before collecting.
- `base_run` in a collection config: the run also reads an earlier run's store and never
  writes it, so v1's 864 Bronze players and every ladder page come from its cache and only the
  4,704 new players are requested.
- `docs/riot-production-key.md`: a draft production-key application, the approved way to
  collect faster.

- Milestones M1-M5 in `docs/requirements.md`: the path from here, each with an owner, a
  dependency and a "done when", so a new session can pick up without a briefing.
- Phase 4d (the Bronze expansion) in the roadmap.

### Changed
- `LayeredStore` moved from `lolret.forward.collect` to `lolret.collect.store`, shared by
  collection runs and the forward test.
- The Bronze collection started and was paused at 20 of 5,568 players (0 failures) for a
  machine restart. Re-running the same command resumes it.

### Notes
- Tried inside training and didn't help: separate models per tier, region or role, region or
  role as inputs, and four blended features. Tier as an input helped slightly but is measured
  after the outcomes. Recorded in `src/lolret/model/AGENTS.md`, not on the site.
- Published churn models report ROC-AUC around 0.76-0.96 on their own data and labels. Ours is
  0.83 on the test set, but almost none compares against a days-since-last-game rule, which
  scores 0.81 here.
- Extra API keys from other accounts were ruled out: Riot allows one key per product.

## [2026-10-25] The snapshot is committed for the site

### Added
- `site/data/snapshot.json`: the anonymised `v1` snapshot (1,104 held-out players), committed
  so the site can be deployed. The owner chose to publish the weekly timeline as is (ADR 0014).

### Changed
- `lolret export` rounds days since the last game to a tenth of a day. At three decimals it
  pinned a player's last game to about 90 seconds, which identified far more than the weekly
  counts.
- The Explorer shows driver values without trailing zeros, so a rounded value doesn't look
  more precise than it is.

## [2026-10-25] Forward test frozen; session checkpoint

### Added
- The forward test's three entries are frozen and their hashes committed in
  `configs/forward.yaml`: the ladder at 07:06 UTC, the nets at 07:17, the candidates at 07:19,
  all for the 3,718 players eligible at 2026-10-22. The features collection took 51,697
  requests in 5 h 51 min with 0 failures.
- `lolret predict` was checked against the real API on three sampled players (one per region),
  printing no identifier: the Riot IDs resolved to the same accounts, two got predictions and
  one, with no game in 28 days, was reported as not covered.

### Changed
- The root `AGENTS.md` "Active work" and the checklist reflect the merged state (#11 to #20).

## [2026-10-25] Dark mode for the site; tuning checked

### Added
- The site has a dark theme with its own colours, following the reader's system setting and
  the navbar toggle; charts re-render with dark colours when the theme changes.

### Notes
- A 40-setting random search over LightGBM's parameters, inside training only, gained at most
  0.002 log loss and 0.007 PR-AUC on fresh folds. Noise, so the hand-set parameters stay.

## [2026-10-25] The site builds in CI

### Added
- `.github/workflows/site.yml`: renders the site on a demo snapshot of random values
  (`python -m lolret.export.demo`) on every PR that touches the site or the export. A test keeps
  the demo's structure equal to a real export's.
- `.github/workflows/pages.yml`: deploys the site to GitHub Pages, only when run by hand, and
  only with a committed snapshot.

### Changed
- `.gitignore` re-includes `site/data/` and ignores only the snapshot file, so publishing it is
  one deleted line.

## [2026-10-25] The site shows the forward test

### Added
- `lolret export --forward configs/forward.yaml` (the default) adds the forward test to the
  snapshot: pending with its dates and frozen hashes, then, once scored, its aggregate results.
  The site's Overview shows whichever it is, so the November result needs only a re-export.

## [2026-10-25] Results by region and tier

### Added
- `metrics.json`, the model card and the site's model card page break the test results down by
  region and by tier (PR-AUC of LightGBM and the recency rule, ROC-AUC, churn). Reporting only:
  each group has 15 to 75 churners, and nothing is chosen from these numbers.

## [2026-10-25] README in 30 seconds

### Changed
- The README opens with the story: the 2024 leak, the fix, the honest result, the frozen
  forward test, and how to try it. The status line moves to Phase 5.

## [2026-10-25] The site

### Added
- `site/`: a Quarto site with Overview, Explorer (filters, search, each player's probability,
  outcome, top drivers and weekly games around the cutoff), Model card (intervals, comparisons
  with the recency rule, a calibration chart) and Developers. Every number comes from the
  snapshot; the banner and Riot's disclaimer are on every page; no horizontal scroll at phone
  width. Built and checked locally, not deployed.
- The snapshot now carries each model's intervals, the comparisons with the recency rule and the
  training-set sizes, for the model card page.

### Changed
- `site/data/snapshot.json` is git-ignored until the owner settles what the timeline shows
  (ADR 0014).

## [2026-10-25] Snapshot export for the site

### Added
- ADR 0014 and `lolret export` (FR4): `data/snapshot/<dataset>/snapshot.json` with the 1,104
  held-out players at the latest cutoff, numbered by a salt drawn per export and never stored:
  region, tier, LightGBM and recency probabilities, outcome, top three SHAP drivers, weekly
  games from 8 weeks before the cutoff to 4 after, and every model's test metrics. Written
  under `data/`; publishing waits for the owner's call on how much timeline to show.

## [2026-10-25] Live prediction for one player

### Added
- `lolret predict --riot-id Name#TAG --platform <server>` (FR6): looks the player up with the
  developer's key, fetches their last 8 weeks into a day cache, builds the features with the
  training code (`extract` and `features.sql`) as of today 00:00 UTC, and prints the ladder's
  churn probability with its three biggest SHAP drivers. The PUUID is never shown.
- `RiotEndpoints.account_by_riot_id` (account-v1) and `account_region_for`.

## [2026-10-25] Candidate features for the forward test

### Added
- ADR 0013: five candidate features (the four break features of ADR 0010, plus
  `repeated_teammates`, found in a training-only look at social ties) in `candidates.sql` and
  `candidates.parquet`, under the same timing rules and leak guard. They stay out of the
  model's 21 features until the forward test decides.
- `lolret train-candidates`: on the 4a test, LightGBM with them scored 0.458 against 0.464,
  level; recorded, deciding nothing.
- `lolret forward predict-candidates`: LightGBM with the candidates enters the forward test as
  a later entry with its own committed hash.

### Changed
- Extraction keeps each match's summoner level and the teammates' PUUIDs (under `data/`).

## [2026-10-25] Neural nets

### Added
- ADR 0012 and `lolret train-nn`: an MLP on the 21 features, a GRU over each example's last
  20 finished matches, and a LightGBM + GRU average, trained with the 4a split, folds and
  Platt calibration, 5 seeds each. Settings were chosen by out-of-fold log loss before the
  test set was scored, and the rule for replacing LightGBM was written down first.
- Result on the test set: MLP 0.458, GRU 0.437, average 0.456 PR-AUC against LightGBM's
  0.464, all within the noise, so LightGBM stays the headline model. The model card shows
  them all.
- `sequences.sql` and `sequences.parquet` (built by `lolret build`), covered by the leak guard.
- `lolret forward predict-nn`: the nets enter the forward test as a later entry, retrained on
  all of `v1`, with their own committed hash.
- `notebooks/train_colab.ipynb`, an optional Colab launcher.

### Changed
- PyTorch (CPU wheels) installs by default, so strict type checks and the CI smoke test run
  everywhere. This amends ADR 0004's optional group.

## [2026-10-25] Forward test started

### Added
- ADR 0011 and `lolret forward collect | predict | score`: predictions at the 2026-10-22 cutoff
  for the 3,718 eligible `v1` players, from the ladder retrained on every labelled `v1`
  example, frozen by a SHA-256 committed in `configs/forward.yaml`. Each step checks the one
  before it, so labels can't be collected before the hash is committed and predictions can't
  be redone once labels exist. Scored after 2026-11-19.
- `tests/test_forward.py`: the whole sequence against a fake Riot API, plus every refusal.

### Changed
- The collector's per-player loop and per-platform runner are reusable helpers
  (`collect_players`, `per_platform`), `extract` takes an `until` horizon, `load_examples` can
  keep unlabelled rows, and `fit_ladder` is shared by `lolret train` and the forward test.
  Behaviour of `collect`, `build` and `train` is unchanged.

## [2026-10-24] Break features tried and dropped

### Added
- ADR 0010: four features aimed at telling a break from quitting (`returns_8w`,
  `longest_gap_days`, `break_vs_longest_gap`, `summoner_level`), tried under a rule set before
  training. LightGBM's PR-AUC rose from 0.464 to 0.476, but neither part of the rule was met,
  so the features were removed. The code stays in commit `40b421a`.
- The dataset notes now ask for the keep rule to be written down before training with a new
  feature.

## [2026-10-24] Task checklist

### Added
- `docs/checklist.md`: every task from the first commit to launch, by roadmap phase, with done
  items ticked and owner-only tasks marked. The roadmap keeps phase status; the checklist breaks
  each phase into tasks.
- The root map and the docs table list it, and `/checkpoint` ticks its boxes.

## [2026-10-24] Exploratory analysis

### Added
- `notebooks/eda.ipynb`: population by region and tier, churn by cutoff, region and tier,
  feature distributions and missing values, each feature against churn, and the signal left
  beyond recency. It reads only the processed dataset and drops `puuid` at load. Outputs are
  stripped on commit, so the findings are written out in the last cell.
- Findings on run `v1`: churn is stable across cutoffs (17-19%); it is 8% in Diamond and 23-25%
  in Silver and Bronze; 69% of churners hadn't played for 7+ days, and inside those groups no
  feature beats AUC 0.60, which is why the models only edge out the recency rule.
- `notebooks` dependency group (pandas, matplotlib, ipykernel, nbconvert), installed with
  `uv sync --group notebooks`, so CI and a plain install stay lean.
- `notebooks/AGENTS.md` with the notebook rules.

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
