# Engineering standards

How work is done in this repo. Adapted from the standards I use at work, minus everything
platform-specific, plus rules added because of what went wrong in the 2024 version.

## Version control

- `main` is always releasable. Work happens on short-lived branches named
  `type/short-description` (for example `feat/riot-client`), merged by pull request.
- CI must pass before merge. Squash-merge, so each PR becomes one commit on `main`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  `type(scope): short description`.
  Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `ci`.
- Commits are authored by the repo owner only. No AI attribution trailers or footers.

## Project structure

```
src/lolret/   the package: all pipeline logic lives here
tests/        pytest; fixtures are recorded, anonymised API responses
configs/      experiment configs (YAML)
notebooks/    exploration and narrative only; they import the package
docs/         requirements, standards, decisions (ADRs)
site/         Quarto site
data/         local only, git-ignored
```

Notebooks never hold pipeline logic. If a notebook cell is needed twice, it moves into
`src/lolret/` with a test.

## Configuration and secrets

- Non-secret constants live in `src/lolret/config.py`.
- Secrets come **only** from environment variables or a git-ignored `.env`.
  `.env.example` documents every variable with an empty value.
- Secrets are typed `SecretStr`, so they never appear in logs, reprs or CLI output.
- Nothing is hardcoded: no keys, webhook URLs, hostnames, passwords or personal IDs.
- On Colab, secrets come from Colab Secrets (`google.colab.userdata`), never from a cell.

## Logging and errors

- Format: `TIMESTAMP [lolret.module] [LEVEL] message`, UTC ISO-8601 timestamps.
- Levels: `DEBUG` / `INFO` / `WARNING` / `ERROR`.
- Every module uses `get_logger(__name__)` from `lolret.log`. No `print` for diagnostics.
- No silent failures: catch only what you can handle, log it, and re-raise or exit non-zero.
  A failed CLI command must exit non-zero so CI or the job runner sees it.

## Notifications: two separate concerns

1. **Errors.** Logged, and the process exits non-zero. CI or the job runner makes failures
   visible. There is no separate error-alerting service.
2. **Operational messages.** Optional: a Discord ping when a long `collect` run finishes.
   The webhook URL comes from `DISCORD_WEBHOOK_URL`. It is never an error channel.

## Data handling and privacy

- Raw API responses and processed datasets stay in `data/` (git-ignored).
- Anything published (site data, fixtures, sample datasets) is anonymised first: player IDs
  are salted hashes, and Riot IDs, PUUIDs and summoner IDs are dropped.
- Model artifacts are saved as plain weights plus config (`state_dict`, LightGBM text
  model), not as pickles of arbitrary objects. They ship as release assets, not commits.
- Files over 1 MB are blocked by pre-commit.

## Point-in-time rule

Every feature function takes an explicit cutoff `as_of` and may only read data at or
before it. The leak-guard test enforces this. This rule exists because the 2024 version
broke it (see [ADR 0003](decisions/0003-point-in-time-labels.md)).

## Testing

- `pytest`, run with `uv run pytest`. Tests need no network and no API key.
- The Riot client is tested against recorded, anonymised responses in `tests/fixtures/`.
- Neural-net code has a CPU smoke test (one epoch on a tiny fixture).
- Tests must pass locally before pushing and in CI before merging.

## Quality gates

| Gate | Local | CI |
|---|---|---|
| Lint and format (ruff) | pre-commit | ✓ |
| File checks, notebook output stripping | pre-commit | ✓ |
| Types (mypy, strict) | `uv run mypy src tests` | ✓ |
| Tests | `uv run pytest` | ✓ (Python 3.12 and 3.13) |
| Secret scan (gitleaks) | pre-commit, staged changes | ✓ full history |

## Riot API compliance

- Respect rate limits and `Retry-After`. Never parallelise beyond one worker per region.
- The public site makes no API calls until a production key is granted.
- The site and README carry Riot's legal disclaimer: *"lolret isn't endorsed by Riot Games
  and doesn't reflect the views or opinions of Riot Games or anyone officially involved in
  producing or managing Riot Games properties. Riot Games, and all associated properties
  are trademarks or registered trademarks of Riot Games, Inc."*

## Documentation

Before a PR is merged:

- `CHANGELOG.md`: add a dated entry with what changed and why, grouped under
  Added / Changed / Fixed / Removed.
- `README.md`: update any section the change affects. The README describes the project as it
  is now, not as it was planned.
- Significant decisions get a short ADR in `docs/decisions/` (context, decision, consequences).
