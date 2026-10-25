# `site/`: the public Quarto site (FR5)

A static site: Overview, Explorer, Model card, Developers. Every number and chart comes from
`data/snapshot.json`, the file `lolret export` writes (ADR 0014). It makes no API calls
(ADR 0002).

**Status:** built and checked locally (2026-10-25), not deployed. The snapshot isn't committed
yet: the owner first decides how much of the weekly timeline to publish (ADR 0014). Deploying
is the owner's call: `pages.yml` runs only by hand.

## Files

- `_quarto.yml`: navbar, Riot's legal disclaimer in the footer, theme, the banner include.
- `assets/banner.html`: the "frozen snapshot, not a live product" banner on every page.
- `assets/light.scss`, `assets/dark.scss`: each theme's colours (Bootstrap defaults and CSS
  variables); `assets/base.scss`: the shared rules (banner, stats, outcome, drivers), which use
  only the variables.
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

CI builds the site on every PR that touches it, on a demo snapshot of random values
(`python -m lolret.export.demo`, `.github/workflows/site.yml`); a test keeps the demo's structure
equal to a real export's.

**Deploying** is `.github/workflows/pages.yml`, run by hand from the Actions tab, once the
snapshot is committed (delete its line in `.gitignore`) and Pages' source is set to GitHub
Actions. It refuses to run without a committed snapshot.

Quarto isn't a Python dependency: install it from quarto.org. On Windows, don't serve
`site/_site` from inside that folder while rendering: the lock makes the render fail.

## Pitfalls

- Charts use Observable Plot. Axis labels sit below the ticks (`labelAnchor: "center"`, a
  larger `marginBottom`), or they collide with the last tick labels.
- Dark mode follows the reader's system setting and the navbar toggle. Charts read the theme
  through a `dark` observer cell and take colours from `pal`, so they re-render on a toggle;
  never hard-code a colour in a chart. Captions say "bright" and "muted", not "dark" and
  "light", so they hold in both themes.
