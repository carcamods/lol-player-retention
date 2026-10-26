# lol-player-retention

Portfolio project: predicts whether a ranked League of Legends player stops playing in the next
28 days, using only what was knowable at prediction time. Python package `lolret` (uv), Riot API
collection into SQLite, a DuckDB point-in-time dataset, classical and neural models, and a
static Quarto site. The owner (Matias) reviews and merges every PR.

This file is a map, read at the start of every session by Claude Code, Codex and other agents
that use `AGENTS.md`. Each module has its own `AGENTS.md` with its context: read it before
changing code in that folder. Read what the task needs, not the whole repo.

## Active work (updated 2026-10-26)

- **Done:** Phases 1-3, 4a, 4b and 4c's freeze; Phase 5 built and the snapshot committed, not
  deployed. Run `v1`: 6,048 players, 11,678 eligible examples, churn 17-19% per cutoff. Never
  delete or rewrite `data/`.
- **Results (4a test, 200 churners):** LightGBM 0.464 PR-AUC against 0.455 for the recency rule,
  not a clear win. MLP 0.458, GRU 0.437 (ADR 0012) and the candidate features 0.458 (ADR 0013)
  are all level with LightGBM, which stays the headline model. Tuning LightGBM gains only noise.
  The EDA explains the ceiling: nothing in a player's history tells a break from quitting.
- **Forward test (ADR 0011), waiting:** three entries frozen on 2026-10-25 for the 3,718 players
  eligible at 2026-10-22, hashes in `configs/forward.yaml`: `ladder` (07:06 UTC), `nn` (07:17),
  `candidates` (07:19). After 2026-11-19 00:00 UTC the owner runs `lolret forward collect
  --labels`, then `lolret forward score`, then `lolret export` for the site. The headline
  question: does LightGBM beat the recency rule? The forward test also decides whether the
  candidate features join the model (ADR 0013).
- **Phase 5:** `lolret predict` (checked against the real API), `lolret export` (ADR 0014) and the
  Quarto site (`site/`, light and dark, built in CI on a demo snapshot) are merged. The owner
  chose to publish the weekly timeline as is (ADR 0014) and `site/data/snapshot.json` is
  committed; `pages.yml` deploys by hand only.
- **Bronze expansion (ADR 0015), collecting:** run `bronze` (`configs/collect-bronze.yaml`)
  adds 4,704 Bronze players on top of v1's, reading v1's store through `base_run`. When it
  finishes: `lolret build -c configs/collect-bronze.yaml`, then judge the rule written in ADR
  0015 (Bronze-only model against the general one, on fresh Bronze test players).
- **Next (owner):** make the repo public, set Pages' source to GitHub Actions and run
  `pages.yml`; apply for a production key (`docs/riot-production-key.md`); score the forward
  test after 2026-11-19. The checklist lists every owner task.

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
uv run lolret collect -c configs/collect-bronze.yaml                # Bronze expansion, ADR 0015
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
