# Tests

`uv run pytest`: no network, no API key, under a minute (the neural-net tests train tiny nets
on CPU). CI runs it on Python 3.12 and 3.13.

## Conventions

- `conftest.py` runs every test from an empty temp directory and clears the settings env vars,
  so a developer's real `.env` is never read. `REPO_ROOT` points at the repo for config files.
- Async tests use `@pytest.mark.anyio` (the `anyio_backend` fixture selects asyncio).
- HTTP is mocked with `respx`. Time-based logic takes injectable clocks and sleeps instead of
  waiting for real.
- `tests/fixtures/*.json` are real Riot responses, anonymised by `scripts/make_fixtures.py`,
  which refuses to write if a real identifier survives. Never paste raw API responses here.
  `test_fixtures.py` checks the fields later phases rely on, so a Riot schema change fails here first.
- mypy (strict) covers the tests too.

## The leak guard

`test_dataset.py::test_leak_guard_features_only_see_data_before_the_cutoff` compares features
from the full data with features from data truncated at each cutoff. Never weaken, skip or
loosen it. When adding a feature, prove the guard still catches a leak by temporarily injecting
one (see `src/lolret/dataset/AGENTS.md`).

## Where tests live

| Area | Files |
|---|---|
| Foundation (settings, logging, CLI) | `test_foundation.py`, `test_cli_collect.py` |
| Riot client | `test_client.py`, `test_ratelimit.py` |
| Collection | `test_collect_config.py`, `test_store.py`, `test_history.py`, `test_collect_run.py`, `test_notify.py` |
| Dataset | `test_dataset.py`, `test_fixtures.py` |
| Models | `test_model.py` |
| Neural nets | `test_nn.py` (CPU smoke test included) |
| Forward test | `test_forward.py` |
