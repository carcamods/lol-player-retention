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
- [ ] After 2026-11-19 00:00 UTC: `lolret forward collect --labels` (about 1.5 h), then
      `lolret forward score`. *Run: Matias*
- [ ] Add the result to the model card and the site.

## Phase 5: launch

- [ ] Snapshot export: salted-hash IDs, JSON for the site, per-player top drivers (FR4).
- [ ] Test that no Riot ID or PUUID survives the export.
- [ ] Quarto site: Overview, Explorer, Model card, Developers (FR5).
- [ ] "Frozen snapshot, not a live product" banner and Riot's legal disclaimer on every page.
- [ ] Site works on mobile.
- [ ] `pages.yml` deploys the site to GitHub Pages.
- [ ] `lolret predict --riot-id Name#TAG` with the developer's own key (FR6).
- [ ] README tells the story in 30 seconds: the 2024 leak, the fix, the result, the demo link.
- [ ] Full-history gitleaks scan returns zero findings.
- [ ] Make the repo public and turn on branch protection (PR and green CI to merge). *Matias*
- [ ] Archive or make private `streamlit_app`, which still serves the 2024 model. *Matias*
- [ ] Link the repo and site from the CV and LinkedIn. *Matias*

## Phase 6: later

- [ ] Apply for a Riot production key, with the live site as the prototype. *Matias*
- [ ] Live lookup API (FR7).
