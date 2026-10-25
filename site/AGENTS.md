# `site/`: the public Quarto site (FR5)

A static site: Overview, Explorer, Model card, Developers. Every number and chart comes from
`data/snapshot.json`, the file `lolret export` writes (ADR 0014). It makes no API calls
(ADR 0002).

**Status:** built and checked locally (2026-10-25), not deployed. The snapshot isn't committed
yet: the owner first decides how much of the weekly timeline to publish (ADR 0014). There is no
deploy workflow yet; deploying is the owner's call.

## Files

- `_quarto.yml`: navbar, Riot's legal disclaimer in the footer, theme, the banner include.
- `assets/banner.html`: the "frozen snapshot, not a live product" banner on every page.
- `assets/style.scss`: the palette (same as the EDA charts) and the stat, outcome and driver
  styles.
- `index.qmd`, `explorer.qmd`, `model-card.qmd`, `developers.qmd`: the pages. The data parts
  are Observable JS cells reading the snapshot.

## Rules that must not break

- **Only the snapshot.** Pages read `data/snapshot.json` and nothing else from the pipeline:
  no PUUIDs, Riot IDs or raw data, ever.
- The banner and the disclaimer stay on every page (Riot's policy, FR5).
- Numbers come from the snapshot, not typed into prose, except the forward-test facts on the
  Overview, which change only when it is scored.
- The site must work at phone width with no horizontal scroll.

## Building

```bash
uv run lolret export -c configs/train.yaml
cp data/snapshot/v1/snapshot.json site/data/snapshot.json   # local copy, git-ignored
quarto preview site                                         # or: quarto render site
```

Quarto isn't a Python dependency: install it from quarto.org. On Windows, don't serve
`site/_site` from inside that folder while rendering: the lock makes the render fail.

## Pitfalls

- Charts use Observable Plot. Axis labels sit below the ticks (`labelAnchor: "center"`, a
  larger `marginBottom`), or they collide with the last tick labels.
- Light theme only for now; a dark theme needs its own chart colours, not an automatic flip.
