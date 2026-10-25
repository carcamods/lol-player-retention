# Requirements

What this project must achieve, for whom, and how we know it's done.
Design decisions behind these requirements are recorded in [`decisions/`](decisions/).

## Goal

A public, honest, reproducible case study that predicts whether a ranked League of Legends
player will **stop playing in the next 28 days**. It is built to show end-to-end data
science and engineering skill: data collection from a rate-limited API, leak-free dataset
design, classical and neural models, honest evaluation, and a usable public demo.

It is a redo of a 2024 bootcamp project. That version reported 89–91% accuracy, but
its features leaked the label (see [ADR 0003](decisions/0003-point-in-time-labels.md)).
Finding and fixing that leak is part of the story this project tells.

## Audiences

| Audience | What they need | Where they get it |
|---|---|---|
| Recruiters, hiring managers | The point in 2 minutes: problem, result, what was built | Site overview |
| Technical reviewers | Method, evaluation, code quality, tests | Model card, repo, CI |
| Developers | Run the pipeline or a prediction with their own Riot key | README, CLI, developer page |

## Data source

**The Riot Games API only.** It is the one sanctioned source of League data. Third-party
stat sites (op.gg and similar) forbid scraping, and the API provides everything needed.

Riot's key policy shapes the product:

- **Development key:** expires every 24 h. For prototyping only.
- **Personal key:** never expires, but only for private use. It powers data collection.
- **Production key:** required for any public product that calls the API. Riot wants a
  working prototype before granting one.

So the public site serves a **frozen, anonymised snapshot**. It makes no API calls.
Live predictions run only from the CLI, with the developer's own key.

## Functional requirements

| ID | Requirement |
|---|---|
| FR1 | **Collect.** `lolret collect` pulls a ladder sample and match history from the Riot API. It honours `X-App-Rate-Limit` and `Retry-After`, retries transient errors, caches raw responses, and resumes after an interruption without re-fetching. |
| FR2 | **Point-in-time dataset.** Each row is a (player, cutoff T) pair. No feature uses data after T. A test fails if any post-T data reaches a feature. Only players active in the 28 days before T are eligible (ADR 0006). |
| FR3 | **Classical models.** Majority class, a recency rule, logistic regression and LightGBM, compared on a temporal, player-grouped holdout. Probabilities are calibrated. Outputs are a saved artifact, `metrics.json` and a model card. |
| FR3b | **Neural nets.** An MLP on the tabular features and a GRU sequence model over each player's last ~20 matches before T. Same splits, same metrics. Trained from a thin Colab notebook that calls the package; the same code runs locally on CPU. |
| FR4 | **Snapshot export.** Player IDs are salted hashes. No Riot IDs or PUUIDs leave the machine. Output is JSON for the site. |
| FR5 | **Site.** Pages: Overview, Explorer, Model card, Developers. The Explorer has search and a dropdown, and shows churn probability, the actual outcome, the top drivers and an activity timeline. Every page shows a "frozen snapshot, not a live product" banner and Riot's legal disclaimer. |
| FR6 | **Developer CLI.** `lolret predict --riot-id Name#TAG` runs a live prediction with the developer's own key. |
| FR7 | *Later phase.* A live lookup API, once Riot grants a production key. |

## Non-functional requirements

- **Reproducible.** `uv.lock`, fixed seeds, one command per pipeline stage.
- **Safe.** No secrets in git, enforced by gitleaks in pre-commit and in CI.
- **Tested.** Tests and lint run in CI and must pass before merge. No test needs network or a key.
- **Free and fast to host.** $0 hosting, no server, no cold starts.
- **Usable.** The site works on mobile.
- **Documented.** README, CHANGELOG and these docs reflect the live state of the project.

## Success criteria

- The models are compared honestly against the recency baseline ("days since last game").
  If they don't beat it on PR-AUC, the site says so: that is still a valid finding.
- The repo is public with a clean history, and the site is live.
- The CV links to the new repo, and the old public repos are archived.

## Out of scope

- Real-time serving in the first release.
- User accounts or authentication.
- Other games.
- Scraping third-party sites.

## Data and ML design (summary)

**Population.** Ranked Solo/Duo players from NA1, EUW1 and KR, sampled and stratified
from Iron to Diamond via `league-v4`. Collection runs per region in parallel, because Riot
rate limits are per region. Players are keyed by `puuid`; `summonerId` is deprecated.

**Cutoffs and label.** Three rolling cutoffs, 28 days apart, each with its label window
fully in the past. `churned` = no game of any queue in (T, T + 28 days].

**Features (data up to T only).**

- Activity counts in windows before T (0–7, 7–14, 14–28, 28–56 days), days since last game,
  games-per-week trend. These come from cheap match-ID calls with time bounds.
- From the last ~15–20 match details before T: win rate, loss streak at T, average duration,
  KDA, remake share, queue mix, champion diversity, main role.
- **Never** `league-v4` wins, losses, LP, `inactive` or `hotStreak`: they are measured at
  collection time, after T, so they would leak.

**Evaluation.**

- Model ladder: majority class → recency rule → logistic regression → LightGBM → MLP → GRU,
  plus a LightGBM + GRU average.
- Metrics: PR-AUC, ROC-AUC, Brier score, calibration plot. Natural class balance; no resampling.
- Split by player, train on earlier cutoffs, test on the latest one.
- Explanations: SHAP for tabular models; integrated gradients per match for the GRU (stretch).

**Data volume.** About 2,000 players per region × 3 cutoffs ≈ 18k examples, at roughly
40–50 API calls per player. Phase 2 measures the real cost and fixes the final numbers.

**Known limitation.** Sampling from the current ladder under-represents players who quit
before the current split started. All cutoffs are chosen after the split start.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 0 | Revoke the 2024 leaked credentials; apply for a Riot personal key | Done |
| 1 | Foundation: repo, docs, tooling, CI | Done |
| 2 | Riot client and `collect` (FR1) | Done; full run in progress |
| 3 | Point-in-time dataset, leak-guard test, EDA (FR2) | Done (run `v1`: 6,048 players, 11,678 eligible examples; EDA in `notebooks/eda.ipynb`) |
| 4a | Classical models, evaluation, model card (FR3) | Done (ADR 0008); no model clearly beats the recency rule; break features tried and dropped (ADR 0010) |
| 4b | Neural nets on Colab (FR3b) | — |
| 4c | Forward test: predict at today's cutoff, collect again 28 days later, compare (ADR 0006) | — |
| 5 | Snapshot export, Quarto site, `predict` CLI, go public (FR4–FR6) | — |
| 6 | Production key and live lookup (FR7) | Later |
