# Checklist

Every task from the first commit to launch, by phase. Phase status lives in the
[roadmap](requirements.md#roadmap); this file breaks each phase into tasks. Tick a box in the
PR that finishes the task.

**Owner.** *Matias*: accounts, keys, reviews, merges and anything that publishes. Everything
else is code or docs, delivered as a PR that Matias reviews.

## Phase 0: security cleanup

- [x] Revoke the credentials leaked in the 2024 repo: GitHub token, Discord webhook, Cloud SQL. *Matias*
- [x] Register a Riot personal API key. *Matias*
- [x] Keep the 2024 repo private: its history still holds the leaked values. *Matias*
- [ ] Make the 2024 `blank-app` repo private. *Matias*

## Phase 1: foundation

- [x] Package, typed settings, logging, CLI skeleton (#1).
- [x] Tooling and CI: uv, ruff, mypy, pytest, pre-commit with gitleaks (#1).
- [x] Requirements, standards and the first ADRs (#1, #2).
- [x] Layered repo memory: module context files, `/checkpoint`, `/adr` (#5).
- [x] Context files renamed to `AGENTS.md` (#7, ADR 0009).

## Phase 2: data collection

- [x] Async Riot client: rate limits per region, `Retry-After`, retries (#3).
- [x] `lolret collect` with a resumable SQLite cache and `lolret status` (#3).
- [x] Pilot run, cost check and anonymised test fixtures (ADR 0005).
- [x] Full run `v1`: 2,016 players in each of NA1, EUW1 and KR, 2026-10-22 to 2026-10-24,
      0 failures.

## Phase 3: dataset

- [x] Point-in-time features and labels, with the eligibility rule (#4, ADR 0006).
- [x] Leak guard test (#4).
- [x] `lolret build` on the full `v1` run: 11,678 eligible examples.
- [x] EDA notebook (`notebooks/eda.ipynb`), reading processed data only:
  - population by region and tier
  - churn rate by cutoff and region
  - feature distributions and missing values
  - each feature against the label
  - the signal left beyond recency (#9)

## Phase 4a: classical models

- [x] Model ladder, held-out evaluation and model card (#6, ADR 0008).
- [x] Train on the full dataset and read the model card: no model clearly beats the recency
      rule yet (README, *First results*).
- [x] Check whether churn really rises at the latest cutoff (37% against 20–24% on the
      first 122 players). It doesn't: 17–19% at every cutoff, and calibration holds.
- [x] Decide: features that tell a break from quitting first, or straight to 4b. Features
      first.
- [x] Break-feature round under a rule set in advance: not met, features removed (ADR 0010).
- [x] Candidate features (break features, account level, repeated teammates) kept apart and
      entered in the forward test, which decides whether they join (ADR 0013).

## Phase 4b: neural nets

- [x] Sequence dataset: each player's last ~20 matches before the cutoff, under the same leak guard
      (ADR 0012).
- [x] MLP on the tabular features.
- [x] GRU over the match sequence, plus the static features.
- [x] Training loop: early stopping, fixed seeds, YAML configs, `state_dict` artifacts.
- [x] CPU smoke test in CI: a few epochs on a tiny fixture, the loss falls, output shapes are right.
- [x] Colab launcher notebook; repo access through Colab Secrets, never written in the notebook.
- [ ] Optional: run the Colab launcher once. CPU training takes minutes, so it isn't needed. *Run: Matias*
- [x] MLP, GRU and a LightGBM + GRU average added to the comparison table and model card: all
      level with LightGBM, which stays the headline model (ADR 0012).
- [ ] Decide on a public Weights & Biases report. *Matias*
- [ ] Stretch: integrated gradients per match (Captum).

## Phase 4c: forward test

Start this as soon as 4a works on the full data (it does since 2026-10-24): it needs 28 days
of waiting, and launch doesn't wait for it.

- [x] Predict for every eligible player at a cutoff of "today". Commit the file's SHA-256 so
      the predictions provably weren't changed after the fact. Cutoff 2026-10-22, 3,718
      players, frozen 2026-10-25 (ADR 0011, `configs/forward.yaml`).
- [x] Enter the 4b neural nets as a later entry, before the labels are collected (ADR 0012).
- [x] Enter LightGBM with five candidate features as a later entry (ADR 0013).
- [ ] After 2026-11-19 00:00 UTC: `lolret forward collect --labels` (about 1.5 h), then
      `lolret forward score`. *Run: Matias*
- [ ] Add the result to the model card and the site: `lolret export`, copy the snapshot into
      `site/data/`, commit.

## Bronze expansion (ADR 0015)

- [x] Rule written before collecting: Bronze-only model against the general one, then against
      the recency rule, on fresh Bronze test players.
- [x] `base_run`, so a run reads an earlier run's store without writing it; checked offline
      that the Bronze sample starts with v1's 72 players in all 12 divisions.
- [ ] Collect `configs/collect-bronze.yaml`: 4,704 new players, about 26 h. Paused 2026-10-26
      at 20 of 5,568 complete; re-run the same command to resume.
- [ ] `lolret build -c configs/collect-bronze.yaml`.
- [ ] Write the ADR 0015 evaluation: v1 and `bronze` examples together, both models with ADR
      0008's protocol, judged on the fresh Bronze test players (new players only).
- [ ] Apply the rule exactly as written, record the result in ADR 0015, and report EUW alone.

## Phase 5: launch

- [x] Snapshot export: salted-hash IDs, JSON for the site, per-player top drivers (FR4,
      ADR 0014).
- [x] Test that no Riot ID or PUUID survives the export (and the `v1` export checked
      against all 6,048 PUUIDs).
- [x] Decide how much of the weekly timeline the site shows: as is (2026-10-25, ADR 0014).
      *Matias*
- [x] Quarto site: Overview, Explorer, Model card, Developers (FR5), built on the snapshot.
- [x] "Frozen snapshot, not a live product" banner and Riot's legal disclaimer on every page.
- [x] Site works on mobile: no horizontal scroll at 390 px.
- [x] Commit the snapshot to `site/data/`, with days since the last game rounded to a tenth
      of a day (ADR 0014).
- [x] CI builds the site on a demo snapshot on every PR that touches it (`site.yml`).
- [x] `pages.yml` deploys the site to GitHub Pages, run by hand only.
- [ ] First deploy: set Pages' source to GitHub Actions, run `pages.yml` (after the repo is
      public, unless the plan has private Pages). *Matias*
- [x] `lolret predict --riot-id Name#TAG` with the developer's own key (FR6).
- [x] `lolret predict` checked against the real API on three sampled players, one per region
      (2026-10-25; no identifier printed).
- [ ] Optional: try `lolret predict` on your own Riot ID. *Matias*
- [x] README tells the story in 30 seconds: the 2024 leak, the fix, the result, the proof.
- [ ] Add the site link to the README once it is live. *Matias*
- [x] Full-history gitleaks scan returns zero findings (2026-10-25: every branch, 26 commits;
      CI repeats it on each PR). Repeat just before going public.
- [ ] Make the repo public and turn on branch protection (PR and green CI to merge). *Matias*
- [ ] Archive or make private `streamlit_app`, which still serves the 2024 model. *Matias*
- [ ] Link the repo and site from the CV and LinkedIn. *Matias*

## Phase 6: later

- [ ] Apply for a Riot production key with `docs/riot-production-key.md`, once the site is
      live. *Matias*
- [ ] Choose the next data round from the Bronze and forward-test results (milestone M5), with
      an ADR and a rule set before collecting. Candidates: EUW-focused expansion; each player's
      rank recorded at every future cutoff; a history longer than 8 weeks. *Matias decides*
- [ ] Live lookup API (FR7).
