# Docs

The repo will be public, so everything here is written for outside readers: plain English,
short sentences, no secrets, no real player identifiers, no employer or client material.

## What lives where

| File | Owns | Update when |
|---|---|---|
| `requirements.md` | goal, requirements, roadmap with phase status | a phase starts or ends, a requirement changes |
| `standards.md` | engineering standards, incl. how we work with AI agents | a convention changes (ask the owner first) |
| `features.md` | every dataset column | `features.sql` changes |
| `decisions/` | ADRs, one decision per file, plus `README.md` (index and template) | a decision is made (`/adr`) |
| `riot-api-registration.md` | Riot key types and application text | key status or registration changes |

`CHANGELOG.md` (repo root) is newest first: a dated `## [YYYY-MM-DD] title` heading with
Added / Changed / Fixed / Removed bullets that say what changed and why. Existing entries are
never rewritten.

## ADRs

- Numbered `NNNN-kebab-title.md`, next number = highest + 1. Never renumber or delete one; if a
  decision is reversed, write a new ADR and mark the old one "Superseded by NNNN".
- Sections: Status, Context, Decision, Consequences (template in `decisions/README.md`).
- Every new ADR gets a one-line row in the index in `decisions/README.md`.
