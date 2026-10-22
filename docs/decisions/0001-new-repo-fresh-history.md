# 0001: New repository with a fresh history

**Status:** Accepted, 2026-10-22

## Context

The 2024 bootcamp version lives in `carcamods/league-of-legends-player-retention`, which was
public from August 2024 to October 2026. Its history contains hardcoded credentials: a
Discord webhook URL, API keys and a database password. Removing them in a new commit would
not help, because they stay readable in every earlier commit. The code was also notebook-only,
with Colab Drive paths and duplicated "ERROR" notebooks.

## Decision

Start a new repository, `lol-player-retention`, with no shared history. No code, data or
notebooks are copied from the old repo; only the lessons are. All leaked credentials are
revoked or rotated regardless.

## Consequences

- The public history is clean from the first commit, and gitleaks runs on every commit
  and in CI to keep it that way.
- The old repo stays private permanently and can be deleted once this one is public.
- The 2024 work is referenced in prose (what it did, what was wrong), not linked.
