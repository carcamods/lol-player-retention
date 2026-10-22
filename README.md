# LoL Player Retention

Predicts whether a ranked **League of Legends** player will stop playing in the next
**28 days**, using only what was knowable at prediction time.

> **Status: Phase 3 of 6, dataset.** `lolret build` turns collected data into point-in-time
> features and labels. The full collection run is in progress. See the [roadmap](docs/requirements.md#roadmap).

## What it does

The pipeline samples ranked players from the Riot Games API and builds a point-in-time
dataset: for each player and cutoff date T, features come only from matches before T, and
the label is whether they played at all in the 28 days after T. Classical models (logistic
regression, LightGBM) and neural nets (MLP, GRU sequence model) are compared against a
simple recency baseline. A static site lets anyone explore predictions on an anonymised
snapshot.

This is a rebuild of my 2024 data-science bootcamp project. The original reported 89–91%
accuracy, but its features leaked the label. [ADR 0003](docs/decisions/0003-point-in-time-labels.md)
explains the leak and how this version prevents it.

## Data flow

```
Riot API ──collect──▶ data/raw/<run>.sqlite (cached responses) ──build──▶ data/processed (features + labels per player × cutoff)
                                                                   │
                                     ┌─────────────────────────────┴───────────┐
                                  train (local)                          train-nn (Colab / CPU)
                                     └──────────────┬──────────────────────────┘
                                          models + metrics.json
                                                    │
                                                 export ──▶ site/data (anonymised snapshot) ──▶ GitHub Pages
```

Only the CLI talks to the Riot API. The public site is static and makes no API calls
([ADR 0002](docs/decisions/0002-static-snapshot-site.md)).

**Collection** ([ADR 0005](docs/decisions/0005-collection-design.md)): players are sampled from
random ladder pages per division. For each player, match IDs are fetched per 7-day bucket, and
full details for the 20 most recent matches before each cutoff. Every response is cached in
SQLite, so a stopped run resumes without re-requesting anything.

## Tech stack

Python 3.12+ · uv · httpx (async) · pydantic · typer · SQLite · ruff · mypy · pytest + respx ·
DuckDB + pyarrow · pre-commit + gitleaks · GitHub Actions. Later phases add LightGBM, SHAP, PyTorch and Quarto.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/carcamods/lol-player-retention.git
cd lol-player-retention
uv sync
uv run pre-commit install
cp .env.example .env        # then add your Riot API key
```

## Configuration

All settings come from environment variables or a git-ignored `.env`
(template: [`.env.example`](.env.example)).

| Variable | Required | Description |
|---|---|---|
| `RIOT_API_KEY` | For `collect` / `predict` | Key from [developer.riotgames.com](https://developer.riotgames.com) |
| `RIOT_RATE_LIMITS` | No | Per-routing-value limits, default `20:1,100:120` (personal/dev key) |
| `DISCORD_WEBHOOK_URL` | No | Pinged when a `collect` run ends |
| `DATA_DIR` | No | Local data directory, default `data` |
| `LOG_LEVEL` | No | `DEBUG` / `INFO` / `WARNING` / `ERROR`, default `INFO` |

`uv run lolret config` shows the effective settings. Secrets show as set or missing, never their values.

## How to run

```bash
uv run lolret --help            # available commands
uv run pytest                   # tests (no network or key needed)
uv run mypy src tests           # type check
uv run pre-commit run --all-files
```

**Build the dataset** (no API calls; works while a run is still going, using finished players):

```bash
uv run lolret build -c configs/collect.yaml   # -> data/processed/v1/{dataset.duckdb, examples.parquet}
```

Features and labels are documented in [docs/features.md](docs/features.md).

**Collect data** (needs `RIOT_API_KEY`):

```bash
uv run lolret collect -c configs/collect-pilot.yaml   # pilot: 15 players, ~20 min
uv run lolret collect -c configs/collect.yaml         # full run: ~6,000 players, ~32 h, ~2 GB
uv run lolret status  -c configs/collect.yaml         # progress, from another terminal
```

Stop with Ctrl+C at any time and re-run the same command to resume. Exit codes: `0` done,
`1` key rejected, `2` some requests still failing (re-run to retry them), `130` interrupted.

Pipeline commands still to come: `train`, `train-nn`, `export`, `predict`.

## Scheduled jobs

None. Collection is started manually.

## Project docs

- [Requirements](docs/requirements.md): goal, audiences, requirements, roadmap
- [Engineering standards](docs/standards.md), including [how this project works with AI agents](docs/standards.md#working-with-ai-agents-layered-repo-memory)
- [Dataset and features](docs/features.md)
- [Decisions](docs/decisions/)
- [Riot API registration](docs/riot-api-registration.md): key types and the application text
- [Changelog](CHANGELOG.md)

## Known fragile points

- **Riot API identifiers.** `summonerId` is deprecated; everything is keyed by `puuid`.
- **Riot rate limits** are per routing value and per key type. Collection must honour `Retry-After`.
- **Season and split resets** can drop inactive players from the ladder, which biases the
  sample toward players who are still active. `season_start` in the config guards the range.
- **Match buckets use game start time.** A game starting just before a cutoff ends after it;
  features must only use matches that ended before the cutoff.

## License and legal

Code is MIT-licensed ([LICENSE](LICENSE)).

lolret isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games
or anyone officially involved in producing or managing Riot Games properties. Riot Games,
and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
