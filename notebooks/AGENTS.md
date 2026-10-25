# Notebooks

Exploration and narrative only. Pipeline logic lives in `src/lolret/` (`docs/standards.md`): if
a cell is needed twice, it moves into the package with a test.

**Status:** `eda.ipynb` done on run `v1` (2026-10-24). `train_colab.ipynb`, the optional Colab
launcher for the neural nets, added with Phase 4b (ADR 0004, ADR 0012).

## Files

- `eda.ipynb`: population, churn by cutoff, region and tier, feature distributions and missing
  values, each feature against churn, and the signal left beyond recency. The findings are
  written out in the last cell.
- `train_colab.ipynb`: a thin launcher. It mounts Google Drive for the processed data,
  clones the repo with a token from Colab Secrets, and runs `lolret train` and
  `lolret train-nn`. Never put a token or data in a cell.

## Rules that must not break

- Read processed data only (`examples.parquet`, found with `lolret.model.train.examples_path`),
  never `data/raw` or the API.
- Drop `puuid` when loading (`SELECT * EXCLUDE (puuid)`), so no output can show a player
  identifier. Show aggregates, never individual players' rows.
- Outputs are stripped on commit (nbstripout), so the numbers that matter go in a markdown cell,
  dated with the run. When the dataset changes, re-run the notebook and update that cell.
- No secrets in cells. On Colab they come from Colab Secrets (`docs/standards.md`).

## Running

- `uv sync --group notebooks` adds pandas, matplotlib, ipykernel and nbconvert. A plain
  `uv sync` removes them again.
- Open the notebook in Jupyter or VS Code with `.venv` as the kernel. The setup cell finds the
  repo root whether it runs from `notebooks/` or from the root.
- Headless check: `uv run --group notebooks jupyter nbconvert --to notebook --execute
  notebooks/eda.ipynb --output-dir <a folder outside the repo>`. Executing in place would write
  outputs into the tracked file.
- ruff lints and formats notebooks too (pre-commit).

## Pitfalls

- Charts share one style, set in the setup cell: light surface, hairline grid, one blue for
  single-series charts, and the matching blue ramp for heatmaps. Keep new charts in it.
- Features that are mostly zero (`aram_share`) collapse into one decile; `deciles()` falls back
  to zero plus quartiles of the rest.
