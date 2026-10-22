# LoL Player Retention

Predicts whether a ranked **League of Legends** player will stop playing in the next
**28 days**, using only what was knowable at prediction time.

> **Status: Phase 1 of 6, foundation.** The repo, standards, tooling and CI are in place.
> Data collection is next. See the [roadmap](docs/requirements.md#roadmap).

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
Riot API ──collect──▶ data/raw (cached responses) ──build──▶ data/processed (features + labels per player × cutoff)
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

## Tech stack

Python 3.12+ · uv · pydantic-settings · typer · ruff · mypy · pytest · pre-commit + gitleaks ·
GitHub Actions. Later phases add httpx, DuckDB, LightGBM, SHAP, PyTorch and Quarto.

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
| `DISCORD_WEBHOOK_URL` | No | Pinged when a long `collect` run finishes |
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

Pipeline commands (`collect`, `build`, `train`, `train-nn`, `export`, `predict`) are added
phase by phase.

## Scheduled jobs

None yet. Collection is run manually.

## Project docs

- [Requirements](docs/requirements.md): goal, audiences, requirements, roadmap
- [Engineering standards](docs/standards.md)
- [Decisions](docs/decisions/)
- [Riot API registration](docs/riot-api-registration.md): key types and the application text
- [Changelog](CHANGELOG.md)

## Known fragile points

- **Riot API identifiers.** `summonerId` is deprecated; everything is keyed by `puuid`.
- **Riot rate limits** are per region and per key type. Collection must honour `Retry-After`.
- **Season and split resets** can drop inactive players from the ladder, which biases the
  sample toward players who are still active. Cutoffs are chosen after the current split start.

## License and legal

Code is MIT-licensed ([LICENSE](LICENSE)).

lolret isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games
or anyone officially involved in producing or managing Riot Games properties. Riot Games,
and all associated properties are trademarks or registered trademarks of Riot Games, Inc.
