# Claude Code instructions: lol-player-retention

Personal portfolio project. Read this first, every session.

## Read first

- `README.md`: what the project does and its current state.
- `docs/requirements.md`: goal, requirements and roadmap. Check which phase is in progress.
- `CHANGELOG.md`: the top few entries.
- For structural changes, refactors or unfamiliar code: `docs/standards.md` and the relevant
  ADRs in `docs/decisions/`.

## How to work

- Read the existing code before writing or changing anything. Never assume structure.
- Ask before decisions that change project structure, the data/label design, or deviate
  from `docs/standards.md`.
- Finish the requested task before anything else. Flag unrelated issues at the end; never
  fix them silently.
- Work on a branch (`type/short-description`) and open a PR. The owner merges.
- Commit messages: Conventional Commits. **No AI attribution** in commits, PRs or docs.
- Never invent credentials. If a key is needed and missing, implement the integration,
  read it from settings, and say what needs to be set.

## Never

- Hardcode or print secrets (keys, webhook URLs, passwords, tokens), including in notebook
  outputs, logs, test fixtures or chat.
- Commit `.env`, anything under `data/`, model artifacts, or raw API responses.
- Publish un-anonymised player data. Riot IDs, PUUIDs and summoner IDs never leave `data/`.
- Write a feature that reads data after its `as_of` cutoff (see ADR 0003).
- Push directly to `main`, make the repo public, or deploy the site. Those are the owner's call.
- Put pipeline logic in notebooks. Notebooks import `lolret`.

## Commands

```bash
uv sync                              # install
uv run pytest                        # tests
uv run mypy src tests                # types
uv run pre-commit run --all-files    # lint, format, secret scan
uv run lolret --help                 # CLI
```

## End of a session that changed the project

1. Add an entry to `CHANGELOG.md`: what changed and why.
2. Update `README.md` and the roadmap status in `docs/requirements.md` if they're affected.
3. Summarise: what was done, what the owner needs to do (keys, merges, Colab runs), and
   open decisions.
