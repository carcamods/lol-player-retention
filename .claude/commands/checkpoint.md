---
description: End-of-session review - record decisions, update changelog and context files, run checks, commit
---
We are wrapping up this working session. Do the following, in order, and report each step.

1. **Decisions.** Review the whole session for durable decisions (approach, data or label design,
   tooling, conventions) that have no ADR yet. Record each one as described in `/adr`. If there
   are none, say so.
2. **Changelog.** Add or extend today's entry at the top of `CHANGELOG.md`: a dated heading and
   Added / Changed / Fixed / Removed bullets that say what changed and why.
3. **Context files.** Update whatever this session made stale:
   - the "Active work" section of the root `CLAUDE.md` (what's done, what's running, next step);
   - the `CLAUDE.md` of every module whose code changed (status, files, rules, tests);
   - phase statuses in the roadmap in `docs/requirements.md`;
   - `README.md`, if commands or usage changed.
   Keep each `CLAUDE.md` short; link to ADRs and docs instead of copying them.
4. **Checks.** Run `uv run ruff check .`, `uv run mypy src tests` and `uv run pytest`. If any
   fail, stop and report instead of committing.
5. **Git.** Show `git status`. Commit on the current feature branch (never `main`) with a
   Conventional Commit message, push, and open or update the PR. Remind the owner to merge it.
