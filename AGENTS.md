# lol-player-retention

Portfolio project: predicts whether a ranked League of Legends player stops playing in the next
28 days, using only what was knowable at prediction time. Python package `lolret` (uv), Riot API
collection into SQLite, a DuckDB point-in-time dataset, classical and neural models, and a
static Quarto site. The owner (Matias) reviews and merges every PR.

This file is a map, read at the start of every session by Claude Code, Codex and other agents
that use `AGENTS.md`. Each module has its own `AGENTS.md` with its context: read it before
changing code in that folder. Read what the task needs, not the whole repo.

## Active work (updated 2026-10-27)

- **Done:** Phases 1-3, 4a, 4b, 4c's freeze and 4d; Phase 5 built, public and deployed (M1).
  Run `v1`: 6,048 players, 11,678 eligible examples, churn 17-19% per cutoff. Never
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
- **Phase 5, M1 done (2026-10-26):** the repo is public and the site is live at
  https://carcamods.github.io/lol-player-retention/ on the committed v1 snapshot (ADR 0014);
  `pages.yml` deploys by hand only. A ruleset on `main` requires a PR and the three CI checks,
  with no bypass and no approval needed.
- **Bronze expansion (ADR 0015), M2 done (2026-10-27):** run `bronze` added 4,704 Bronze
  players on top of v1's (9,081 eligible examples). On 750 fresh Bronze test players (179
  churned), Bronze-only 0.570 PR-AUC against the general model's 0.566: the rule wasn't met, so
  one model for every tier stays. The general model against the recency rule: +0.028 (95% CI
  -0.021 to +0.084). `lolret train-bronze` reproduces it. The EUW-focused expansion dropped
  out of M5. Open for the owner: `gap_hours_median` depends slightly on what else is cached
  (`src/lolret/dataset/AGENTS.md`).
- **Tried inside training, didn't help (2026-10-26):** separate models per tier, region or
  role, region or role as inputs, four blended features. Numbers in `src/lolret/model/AGENTS.md`.
  Tier as an input helped slightly but is measured after the outcomes, so it can't be used yet.
- **No production key (ADR 0016, 2026-10-27):** the owner won't apply. Collection stays on the
  current key's limits, M3 is dropped and the live lookup (FR7) is deferred.
- **Next:** the milestones in `docs/requirements.md#milestones`: M4 score the forward test after
  2026-11-19, then M5 choose the next data round (rank at every cutoff, or a longer history).
  The checklist has every task.

## Where things live (read on demand)

| Need | Read |
|---|---|
| Goal, requirements, roadmap, milestones from here | `docs/requirements.md` |
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
uv run lolret train-bronze -c configs/train.yaml                    # Bronze expansion, ADR 0015
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
