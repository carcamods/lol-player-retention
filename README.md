# LoL Player Retention

Predicts whether a ranked **League of Legends** player will stop playing in the next
**28 days**, using only what was knowable at prediction time.

## In 30 seconds

- **The leak.** My 2024 bootcamp version of this project reported 91% accuracy. It was fake:
  its features were built from the whole date range, so players who had quit had empty "late"
  features and the model read the answer off them.
- **The fix.** This rebuild makes every example a (player, date) pair whose features use only
  data from before that date, and a property test deletes everything after the date and checks
  that no feature moves. 6,048 ranked players from NA, EUW and KR, collected from Riot's API.
- **The result.** Honest and modest: the best model (LightGBM, PR-AUC 0.464) barely beats
  ranking players by days since their last game (0.455). Neural nets and new features didn't
  change that, because nothing in a player's history tells a break from quitting. Every
  choice was made inside training, and every rule for keeping a feature or model was written
  down before the test.
- **The proof.** Predictions for 3,718 players were frozen by a committed SHA-256 before their
  outcomes happened; they are scored after 2026-11-19.
- **Try it.** `lolret predict --riot-id Name#TAG` predicts for any player with your own key; a
  static site with an explorer of held-out players is ready to publish ([`site/`](site/)).

> **Status: Phase 5 of 6, launch.** Models, forward test, live prediction, snapshot export and
> the site are built; publishing waits on one privacy decision
> ([ADR 0014](docs/decisions/0014-snapshot-export.md)). See the
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

Models on 1,104 held-out players at the latest cutoff (2026-09-24), 18.1% of whom stopped
playing. 95% bootstrap intervals in parentheses.

| Model | PR-AUC | ROC-AUC | Brier |
|---|---|---|---|
| Majority class | 0.181 | 0.500 | 0.148 |
| Recency rule (days since the last game) | 0.455 (0.393, 0.528) | 0.814 (0.784, 0.843) | 0.120 |
| Logistic regression | 0.452 (0.389, 0.527) | 0.819 (0.790, 0.848) | 0.119 |
| LightGBM | 0.464 (0.400, 0.541) | 0.825 (0.797, 0.854) | 0.118 |
| MLP | 0.458 (0.392, 0.532) | 0.821 (0.792, 0.851) | 0.118 |
| GRU over the last 20 matches | 0.437 (0.373, 0.508) | 0.816 (0.788, 0.845) | 0.120 |
| LightGBM + GRU average | 0.456 (0.392, 0.533) | 0.824 (0.795, 0.853) | 0.118 |

No model clearly beats the recency rule yet: LightGBM's PR-AUC gain is +0.010 (95% CI -0.031
to +0.055). Its probabilities are well calibrated, and its strongest signals are games in the
last 7 days and days since the last game. The neural nets ([ADR 0012](docs/decisions/0012-neural-nets.md))
are level with LightGBM: the GRU looked slightly better inside training and slightly worse
here, and a 200-churner test set can't separate them, so LightGBM stays the headline model.
Five candidate features (the break features below, account level, and how many teammates a
player keeps queueing with) are level too, at 0.458; the forward test decides whether they
join ([ADR 0013](docs/decisions/0013-candidate-features.md)).

The [exploratory analysis](notebooks/eda.ipynb) shows why. 69% of churners hadn't played for a
week or more at the cutoff, and among those players no feature separates a break from quitting
much better than recency does (AUC 0.60 at best inside those groups). In-game statistics such as
win rate and KDA carry almost no signal at all. Four features aimed at that gap (break history,
the longest previous gap, account level) lifted LightGBM to 0.476, but didn't pass the rule set
before training, so they were dropped ([ADR 0010](docs/decisions/0010-break-features.md)).

## Forward test

A test set that has been looked at several times is no longer quite fresh, so the models also
face a forward test ([ADR 0011](docs/decisions/0011-forward-test.md)). The ladder was retrained
on all of run `v1` and predicted, for each of the 3,718 players who had played in the 4 weeks
before 2026-10-22, whether they would play in the 4 weeks after it. The predictions were frozen
on 2026-10-25, before any of those weeks was collected, and the file's SHA-256 is committed in
[`configs/forward.yaml`](configs/forward.yaml), so they can't be changed after the fact. The
outcomes are collected after 2026-11-19. The question, set before freezing: does LightGBM beat
the recency rule on them? Two later entries, frozen the same way before any outcome was
collected, ask whether the neural nets or five candidate features beat LightGBM.

## The site

A static [Quarto](https://quarto.org) site in [`site/`](site/) shows the snapshot: an overview of
the results, an explorer with every held-out player's prediction next to what actually
happened, the model card and a developer page. It reads only the anonymised snapshot from
`lolret export` and makes no API calls. It is built locally and not yet deployed (see
[ADR 0014](docs/decisions/0014-snapshot-export.md) for the one decision left before publishing).

```bash
uv run lolret export -c configs/train.yaml
cp data/snapshot/v1/snapshot.json site/data/snapshot.json
quarto preview site
```

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
DuckDB + pyarrow · scikit-learn · LightGBM · PyTorch (CPU) · pandas + matplotlib (notebooks) ·
pre-commit + gitleaks · GitHub Actions. Phase 5 adds Quarto.

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
| `RIOT_API_KEY` | For `collect`, `forward collect` and `predict` | Key from [developer.riotgames.com](https://developer.riotgames.com) |
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

**Explore the data** (after `build`):

```bash
uv sync --group notebooks   # pandas, matplotlib and a Jupyter kernel
```

Then open [`notebooks/eda.ipynb`](notebooks/eda.ipynb) in Jupyter or VS Code with the project's
`.venv`. Outputs aren't committed; the findings are written out at the end of the notebook.

**Train and evaluate the classical models** (after `build`):

```bash
uv run lolret train -c configs/train.yaml   # -> data/models/v1/{models.json, lightgbm.txt, metrics.json, model_card.md}
```

The test set is 30% of players, held out completely, at the latest cutoff. Every metric comes
with a 95% bootstrap interval, and the model card says whether each model beats the recency
rule ("days since the last game"). Design: [ADR 0008](docs/decisions/0008-classical-model-evaluation.md).

**Train the neural nets** (after `train`; CPU, a few minutes):

```bash
uv run lolret train-nn -c configs/train_nn.yaml   # -> data/models/v1/nn/, adds MLP and GRU to the model card
```

Same split, folds and calibration as the classical models; settings were chosen inside
training ([ADR 0012](docs/decisions/0012-neural-nets.md)). `notebooks/train_colab.ipynb` runs
the same commands on Google Colab.

**Run the forward test** (needs `RIOT_API_KEY`; design in
[ADR 0011](docs/decisions/0011-forward-test.md)):

```bash
uv run lolret forward collect -c configs/forward.yaml            # features at the cutoff (~4-6 h)
uv run lolret forward predict -c configs/forward.yaml            # freeze; commit the printed hash
uv run lolret forward predict-nn -c configs/forward.yaml         # later entry: the nets
uv run lolret forward predict-candidates -c configs/forward.yaml # later entry: candidate features
uv run lolret forward collect -c configs/forward.yaml --labels   # after the 28 days (~1.5 h)
uv run lolret forward score   -c configs/forward.yaml            # -> data/forward/<name>/report.md
```

Each step refuses to run out of order: no labels before the hash is committed, no predictions
once labels exist, and no score if a file doesn't match its hash.

**Predict for one player, live** (needs `RIOT_API_KEY` and `lolret train`):

```bash
uv run lolret predict --riot-id "Name#TAG" --platform euw1
```

It fetches the player's last 8 weeks (about 30 requests, cached for the day), builds the
features with the same code as training, as of today 00:00 UTC, and prints the churn
probability with its three biggest drivers. Players who haven't played in the last 4 weeks
aren't covered. The public site never calls the API
([ADR 0002](docs/decisions/0002-static-snapshot-site.md)).

**Collect data** (needs `RIOT_API_KEY`):

```bash
uv run lolret collect -c configs/collect-pilot.yaml   # pilot: 15 players, ~20 min
uv run lolret collect -c configs/collect.yaml         # full run: ~6,000 players, ~35 h, ~2.4 GB
uv run lolret status  -c configs/collect.yaml         # progress, from another terminal
```

Stop with Ctrl+C at any time and re-run the same command to resume. Exit codes: `0` done,
`1` key rejected, `2` some requests still failing (re-run to retry them), `130` interrupted.

**Export the snapshot for the site** (after `train`; no API calls):

```bash
uv run lolret export -c configs/train.yaml   # -> data/snapshot/v1/snapshot.json
```

The 1,104 held-out players, numbered "Player 0001"... by a salt that is drawn per export and
never stored, with each prediction, the outcome, the top drivers and weekly activity. It stays
under `data/` until it is deliberately copied into the site
([ADR 0014](docs/decisions/0014-snapshot-export.md)).

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
