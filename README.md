# LoL Player Retention

Predicts whether a ranked **League of Legends** player will stop playing in the next
**28 days**, using only what was knowable at prediction time.

> **Status: Phase 4 of 6, models.** The full collection run is done (6,048 players, 11,678
> eligible examples) and the classical models are trained and evaluated: see
> [first results](#first-results). Next: exploratory analysis, then neural nets. See the
> [roadmap](docs/requirements.md#roadmap).

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

## First results

Classical models on 1,104 held-out players at the latest cutoff (2026-09-24), 18.1% of whom
stopped playing. 95% bootstrap intervals in parentheses.

| Model | PR-AUC | ROC-AUC | Brier |
|---|---|---|---|
| Majority class | 0.181 | 0.500 | 0.148 |
| Recency rule (days since the last game) | 0.455 (0.393, 0.528) | 0.814 (0.784, 0.843) | 0.120 |
| Logistic regression | 0.452 (0.389, 0.527) | 0.819 (0.790, 0.848) | 0.119 |
| LightGBM | 0.464 (0.400, 0.541) | 0.825 (0.797, 0.854) | 0.118 |

Neither model clearly beats the recency rule yet: LightGBM's PR-AUC gain is +0.010 (95% CI
-0.031 to +0.055). Its probabilities are well calibrated, and its strongest signals are games in
the last 7 days and days since the last game. The next phases test whether richer features or a
sequence model add signal beyond recency.

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
DuckDB + pyarrow · scikit-learn · LightGBM · pre-commit + gitleaks · GitHub Actions. Later phases add
PyTorch and Quarto.

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

**Train and evaluate the classical models** (after `build`):

```bash
uv run lolret train -c configs/train.yaml   # -> data/models/v1/{models.json, lightgbm.txt, metrics.json, model_card.md}
```

The test set is 30% of players, held out completely, at the latest cutoff. Every metric comes
with a 95% bootstrap interval, and the model card says whether each model beats the recency
rule ("days since the last game"). Design: [ADR 0008](docs/decisions/0008-classical-model-evaluation.md).

**Collect data** (needs `RIOT_API_KEY`):

```bash
uv run lolret collect -c configs/collect-pilot.yaml   # pilot: 15 players, ~20 min
uv run lolret collect -c configs/collect.yaml         # full run: ~6,000 players, ~35 h, ~2.4 GB
uv run lolret status  -c configs/collect.yaml         # progress, from another terminal
```

Stop with Ctrl+C at any time and re-run the same command to resume. Exit codes: `0` done,
`1` key rejected, `2` some requests still failing (re-run to retry them), `130` interrupted.

Pipeline commands still to come: `train-nn`, `export`, `predict`.

## Scheduled jobs

None. Collection is started manually.

## How this project is built

I develop it with an AI coding agent, and the repo is the agent's memory. A short
root [`AGENTS.md`](AGENTS.md) is read every session, each module's `AGENTS.md` is read only when
that code is touched, decisions are logged once as ADRs, and an end-of-session `/checkpoint`
keeps it all current. I call this *layered repo memory*. It is a form of what is usually called
context engineering, and it uses `AGENTS.md`, the open format most coding agents read, so it
isn't tied to one tool. The rules that matter most are enforced by tests and CI, not prompts:
the leak guard, strict types and secret scanning. I review and merge every change. Details:
[standards](docs/standards.md#working-with-ai-agents-layered-repo-memory),
[ADR 0007](docs/decisions/0007-layered-repo-memory.md) and [ADR 0009](docs/decisions/0009-agents-md.md).

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
