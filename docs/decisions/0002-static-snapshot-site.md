# 0002: Public demo as a static snapshot site

**Status:** Accepted, 2026-10-22. Production-key plan dropped by [0016](0016-no-production-key.md):
no application, so no live lookup (FR7) for now.

## Context

The demo should let a visitor pick or search for a player and see a prediction. A live
"enter any Riot ID" box needs the Riot API at request time, and Riot's policy forbids
running a public product on a personal key; a production key requires a working prototype.
Free Python hosts (Streamlit Cloud, Render) also sleep when idle, so a visitor's first load
can take 30–60 seconds.

## Decision

- The public site is a **Quarto static site** on GitHub Pages, with Observable JS for the
  interactive Explorer. It reads a frozen, anonymised snapshot exported by the pipeline.
- Live predictions are a **developer feature**: `lolret predict --riot-id Name#TAG`, run
  locally with the developer's own key.
- Once the site is live, it serves as the prototype for a production-key application. If
  granted, a small live-lookup API is added (FR7).

## Consequences

- $0 hosting, no server, no cold starts, and no secret anywhere near the public site.
- The site must say clearly that it shows a frozen snapshot, not a live product.
- Because the snapshot's label windows are in the past, the Explorer can show each
  prediction next to what actually happened.
- Players in the snapshot are anonymised (salted hashes), so the dropdown shows IDs such
  as "Player 0042 · Gold II · EUW", not Riot IDs.
