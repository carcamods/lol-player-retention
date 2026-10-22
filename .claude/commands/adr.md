---
description: Record a decision from this conversation as a new ADR and add it to the index
argument-hint: "[short title]"
---
Record the decision we just made as an architecture decision record. Title: $ARGUMENTS (if
empty, propose one).

1. Find the next number: the highest `docs/decisions/NNNN-*.md` plus one.
2. Write `docs/decisions/NNNN-kebab-case-title.md` with the template in
   `docs/decisions/README.md` (Status, Context, Decision, Consequences). Use only facts from this
   conversation and the repo. If something is ambiguous, ask before writing.
3. Add a one-line row for it to the index in `docs/decisions/README.md`.
4. If it reverses an earlier ADR, mark that one "Superseded by NNNN" (don't rewrite it).
5. If it changes a module's rules, update that module's `CLAUDE.md`. If it changes requirements
   or the roadmap, update `docs/requirements.md`.
