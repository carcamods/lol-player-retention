# 0016: No production-key application; collection stays on the current key

**Status:** Accepted, 2026-10-27

## Context

ADR 0002 made the public site a static snapshot and planned it as the prototype for a
production-key application: if Riot granted the key, a small live-lookup API would follow
(FR7). `docs/riot-production-key.md` was drafted on 2026-10-26, and milestone M3 was to submit
it once the site was live. The site went live the same day (M1).

The key the project uses allows 20 requests per second and 100 per 2 minutes, per region. A
production key starts at 500 per 10 seconds and 30,000 per 10 minutes
(`docs/riot-api-registration.md`). At the current limits, run `v1` (6,048 players) took about
35 hours and run `bronze` (4,704 new players) about 26, with the three platforms in parallel.
Milestone M5 listed M3 as what would make the next data round fast.

Riot requires a production key only for a public product that calls the API. The site makes no
API calls (ADR 0002), so nothing published needs one.

## Decision

- **No production-key application.** The owner decided on 2026-10-27 to keep collecting on the
  current key, at its rate limits, as for `v1` and `bronze`.
- **Milestone M3 is dropped.**
- **The live lookup API (FR7) stays deferred, with no date:** it needs a production key.
- `docs/riot-production-key.md` stays as a draft in case this changes. Applying later would be a
  new ADR that supersedes this one.

## Consequences

- No code changes. `RIOT_RATE_LIMITS` keeps its default (`20:1,100:120`).
- The next data round (M5) is planned at the current limits. As a guide, about 5,000 new players
  took 26 hours across the three platforms, run in the owner's terminal with the laptop awake.
  Its ADR states the expected duration before collecting.
- The site stays a frozen snapshot, and `lolret predict` with the developer's own key stays the
  only live prediction (FR6).
- ADR 0002's last decision (apply for a production key, then add FR7) no longer holds; the rest
  of ADR 0002 stands. ADR 0002 is marked as amended by this one.
