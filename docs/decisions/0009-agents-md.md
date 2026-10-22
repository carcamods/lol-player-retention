# 0009: Context files are named AGENTS.md

**Status:** Accepted, 2026-10-22. Amends the file names in ADR 0007.

## Context

ADR 0007 put the layered repo memory in `CLAUDE.md` files, the name Claude Code reads.
`AGENTS.md` is an open format for the same purpose. Most coding agents read it (Codex, Cursor,
GitHub Copilot and others), and since December 2025 it has been stewarded by the Agentic AI
Foundation under the Linux Foundation.

Since v2.1.277, Claude Code reads `AGENTS.md` too, as long as there is no `CLAUDE.md`,
`.claude/CLAUDE.md` or `CLAUDE.local.md` in the working directory or any folder above it. It
reads the root file at session start, and a subfolder's file when it opens a file there with its
Read tool. Keeping both names would mean duplicated files that drift apart, or context that only
one tool sees, in a repo that is meant to be public.

## Decision

- Every context file is named `AGENTS.md`: the root map and the module files in
  `src/lolret/riot/`, `src/lolret/collect/`, `src/lolret/dataset/`, `tests/` and `docs/`. The
  layers and their content (ADR 0007) don't change.
- The repo has no `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md`. Any of them would make
  Claude Code ignore every `AGENTS.md`.
- The root map tells agents to read a module's `AGENTS.md` before changing code there. Tools
  differ in whether they load subfolder files by themselves (Claude Code does it only when it
  opens a file with its Read tool), so the instruction makes the module layer work everywhere.
- The `/checkpoint` and `/adr` commands stay in `.claude/commands/`. They are Claude Code
  workflow, not context, and their steps are also written down in `docs/standards.md`.

## Consequences

- One set of files serves every agent, with nothing to keep in sync.
- Claude Code before v2.1.277, or with its built-in `AGENTS.md` support turned off, sees no
  project context. A `CLAUDE.md` that imports `@AGENTS.md` would fix that, but one would be
  needed in every folder that has an `AGENTS.md`, so the repo doesn't add them.
- Claude Code's `InstructionsLoaded` hooks don't fire for `AGENTS.md`. This repo uses none.
- Older changelog entries and ADR 0007 keep the old name: history isn't rewritten.
