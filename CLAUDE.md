# lol-player-retention

Portfolio project: predicts whether a ranked League of Legends player stops playing in the next
28 days, using only what was knowable at prediction time. Python package `lolret` (uv), Riot API
collection into SQLite, a DuckDB point-in-time dataset, classical and neural models, and a
static Quarto site. The owner (Matias) reviews and merges every PR.

This file is a map, loaded every session. Context for each module lives in that module's
`CLAUDE.md` and loads only when you open files there, so read what the task needs, not the
whole repo.

## Active work (updated 2026-10-22)

- **Done:** Phase 1 foundation, Phase 2 collection, Phase 3 dataset (`lolret build`).
- **In progress:** collection run `v1` on the owner's machine, started 2026-10-22 18:17 UTC,
  about 32 h. Check it with `lolret status -c configs/collect.yaml`. Never delete or rewrite
  `data/`, and don't change `configs/collect.yaml` while the run is going.
- **Next:** when the run finishes, `lolret build -c configs/collect.yaml`, then the EDA
  notebook (rest of Phase 3), then Phase 4a classical models. Modelling can start earlier on
  partial data: `build` only uses players whose collection finished.
- **Later:** 4b neural nets on Colab, 4c forward test, 5 site and launch. See the roadmap.

## Where things live (read on demand)

| Need | Read |
|---|---|
| Goal, requirements, roadmap | `docs/requirements.md` |
| Why something is the way it is | `docs/decisions/README.md` (index), then only the relevant ADR |
| What changed recently | the top ~40 lines of `CHANGELOG.md` |
| Feature and label definitions | `docs/features.md` |
| Engineering standards, before structural changes | `docs/standards.md` |
| A module's purpose, rules and tests | its `CLAUDE.md`: `src/lolret/riot/`, `src/lolret/collect/`, `src/lolret/dataset/`, `tests/`, `docs/` |

## Commands

```bash
uv sync                                   # install
uv run pytest                             # tests: no network, no key
uv run mypy src tests                     # types (strict)
uv run pre-commit run --all-files         # ruff, format, file checks, gitleaks
uv run lolret status -c configs/collect.yaml
uv run lolret build  -c configs/collect.yaml
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

## Ending a session

Run `/checkpoint`: it logs decisions, updates the changelog, refreshes this file's "Active
work" and the touched modules' `CLAUDE.md`, runs the checks and commits. Use `/adr` to record a
decision as soon as it's made.
