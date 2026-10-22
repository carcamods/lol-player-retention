# 0007: Layered repo memory for AI-assisted development

**Status:** Accepted, 2026-10-22. File names amended by [0009](0009-agents-md.md): the context
files are now `AGENTS.md` instead of `CLAUDE.md`.

## Context

The project is built across many Claude Code sessions. Without a structure, each session either
re-reads large parts of the repo (slow and expensive) or starts with too little context and
makes changes in the wrong place. Chat history and the agent's local memory don't survive a
change of machine or folder: the memory from the session that started this project was tied to
a different folder and would not have reached sessions opened in this repo.

The owner has used this approach in another project with good results, so it is adapted here
rather than designed from scratch.

## Decision

- **The repo is the memory.** Anything a future session needs is a committed file.
- **Root `CLAUDE.md` is a short map**, loaded every session: purpose, an "Active work" section
  (done, running, next), where things live, and the rules that always apply.
- **Each module has its own `CLAUDE.md`** (`riot`, `collect`, `dataset`, `tests`, `docs`; later
  `model`, `nn`, `site`): purpose, status, rules that must not break, pitfalls, tests to run.
  Claude Code loads these only when files in that folder are opened.
- **Decisions are ADRs** with an index (`docs/decisions/README.md`), so a session reads the
  index and opens only the ADR it needs.
- **`/checkpoint`** ends a session: record decisions, update the changelog, refresh "Active
  work" and the touched modules' `CLAUDE.md`, run the checks, commit on the branch.
  **`/adr`** records a decision when it's made.
- Rules that must never be missed stay in the root `CLAUDE.md` instead of folder-scoped rule
  files, which are known to load unreliably.
- Personal and temporary local notes stay out of git, in the agent's local memory.

Not adopted from the original: committing straight to `main` (it was built for two people on
one docs repo; here, PRs and CI stay) and an `AGENTS.md` mirror for other agents (only Claude
Code is used).

## Consequences

- New sessions start from the map plus the module they work in, not the whole codebase.
- Module `CLAUDE.md` files must stay short and current. `/checkpoint` updates them; anything
  copied from elsewhere should become a link.
- These files are public with the repo. They document how the project is engineered, including
  its AI-assisted workflow, and contain no secrets or personal data.
