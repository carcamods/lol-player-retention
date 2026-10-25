# lol-player-retention

Portfolio project: predicts whether a ranked League of Legends player stops playing in the next
28 days, using only what was knowable at prediction time. Python package `lolret` (uv), Riot API
collection into SQLite, a DuckDB point-in-time dataset, classical and neural models, and a
static Quarto site. The owner (Matias) reviews and merges every PR.

This file is a map, read at the start of every session by Claude Code, Codex and other agents
that use `AGENTS.md`. Each module has its own `AGENTS.md` with its context: read it before
changing code in that folder. Read what the task needs, not the whole repo.

## Active work (updated 2026-10-24)

- **Done:** Phase 1 foundation, Phase 2 collection, Phase 3 dataset (`lolret build`) and EDA
  (`notebooks/eda.ipynb`), Phase 4a classical models (`lolret train`, ADR 0008). Run `v1` finished 2026-10-24: 6,048 players,
  0 failures, 11,678 eligible examples, churn 17-19% at every cutoff. Never delete or rewrite
  `data/`.
- **Results:** on the test set LightGBM reaches PR-AUC 0.464 against 0.455 for the recency
  rule, and the gain's 95% interval includes zero, so no model clearly beats recency yet
  (README; full model card in `data/models/v1/`). The EDA shows why: 69% of churners hadn't
  played for 7+ days, and inside those groups no feature beats AUC 0.60; in-game statistics
  carry almost no signal anywhere.
- **Feature round (ADR 0010):** four break features lifted LightGBM to PR-AUC 0.476 but
  failed the rule set before training, so they were removed (code kept in commit `40b421a`).
- **Forward test (ADR 0011):** started 2026-10-25 at cutoff 2026-10-22. Predictions for the
  3,718 eligible players are frozen and their SHA-256 is committed in `configs/forward.yaml`.
  After 2026-11-19 the owner runs `lolret forward collect --labels`, then `lolret forward score`.
- **Neural nets (ADR 0012):** MLP, GRU over the last 20 matches, and a LightGBM + GRU
  average, trained on CPU with the 4a protocol (`lolret train-nn`). All level with LightGBM
  on the test set (GRU 0.437, MLP 0.458), so LightGBM stays the headline model. The nets are
  entered in the forward test as a later entry.
- **Candidate features (ADR 0013):** the four break features plus `repeated_teammates`, kept in
  `candidates.parquet` apart from `FEATURES`. Level with LightGBM on the 4a test (0.458), which
  decides nothing; entered in the forward test, which decides whether they join the model.
- **Phase 5 started:** `lolret predict --riot-id Name#TAG` (FR6) predicts live for one player
  with the developer's key, through the training feature code. `lolret export` (FR4, ADR 0014)
  writes the anonymised snapshot of the 1,104 held-out players under `data/`; the owner decides
  how much of the weekly timeline to publish before it goes into the site.
- **Site (`site/`):** the four Quarto pages, built and checked locally on the snapshot, not
  deployed. Waiting on the ADR 0014 timeline decision before the snapshot is committed.
- **Next (owner):** decide the timeline question, then publish and deploy; score the forward
  test after 2026-11-19. See the roadmap and the checklist.

## Where things live (read on demand)

| Need | Read |
|---|---|
| Goal, requirements, roadmap | `docs/requirements.md` |
| Every task by phase, what's left and who does it | `docs/checklist.md` |
| Why something is the way it is | `docs/decisions/README.md` (index), then only the relevant ADR |
| What changed recently | the top ~40 lines of `CHANGELOG.md` |
| Feature and label definitions | `docs/features.md` |
| Engineering standards, before structural changes | `docs/standards.md` |
| A module's purpose, rules and tests | its `AGENTS.md`: `src/lolret/riot/`, `src/lolret/collect/`, `src/lolret/dataset/`, `src/lolret/model/`, `src/lolret/nn/`, `src/lolret/forward/`, `src/lolret/live/`, `src/lolret/export/`, `site/`, `notebooks/`, `tests/`, `docs/` |

## Commands

```bash
uv sync                                   # install (includes CPU PyTorch)
uv sync --group notebooks                 # plus pandas, matplotlib, Jupyter kernel
uv run pytest                             # tests: no network, no key
uv run mypy src tests                     # types (strict)
uv run pre-commit run --all-files         # ruff, format, file checks, gitleaks
uv run lolret status -c configs/collect.yaml
uv run lolret build  -c configs/collect.yaml
uv run lolret train  -c configs/train.yaml
uv run lolret train-nn -c configs/train_nn.yaml                     # MLP and GRU, after train
uv run lolret train-candidates -c configs/train.yaml                # candidate features, ADR 0013
uv run lolret predict --riot-id Name#TAG --platform euw1           # live, with your own key
uv run lolret export -c configs/train.yaml                          # snapshot for the site
uv run lolret forward collect|predict|score -c configs/forward.yaml   # forward test, ADR 0011
```

## Rules that always apply

- **Point in time.** A feature for cutoff T reads only data from before T. The leak guard in
  `tests/test_dataset.py` enforces it and must never be weakened (ADR 0003, ADR 0006).
- **Secrets.** Keys and webhook URLs come only from `.env` via settings. Never hardcode, log,
  print or paste them, including in fixtures, notebooks and chat.
- **Data.** Nothing under `data/`, no model artifacts and no raw API responses are committed.
  Riot IDs, PUUIDs and summoner IDs never leave `data/`; anything published is anonymised.
- **Scope.** Do the task asked. Keep changes inside the module you're working in. Flag
  unrelated issues at the end instead of fixing them. Ask before changing project structure,
  the data or label design, or anything in `docs/standards.md`.
- **Git.** Work on a `type/short-description` branch and open a PR; never push to `main`,
  make the repo public or deploy. Conventional Commits. No AI attribution anywhere.
- **Before committing:** the touched module's tests, then the full suite, mypy and pre-commit.
- **Context files are `AGENTS.md`.** Never add a `CLAUDE.md`, `.claude/CLAUDE.md` or
  `CLAUDE.local.md`: any of them makes Claude Code stop reading every `AGENTS.md` (ADR 0009).

## Ending a session

Run `/checkpoint`: it logs decisions, updates the changelog, refreshes this file's "Active
work" and the touched modules' `AGENTS.md`, runs the checks and commits. Use `/adr` to record a
decision as soon as it's made.
