# `lolret.live`: live prediction for one player (FR6)

`lolret predict --riot-id Name#TAG --platform euw1` looks a player up with the developer's own
key and prints the ladder's churn probability and its top drivers. Live predictions stay a
developer feature: the public site serves a frozen snapshot (ADR 0002).

**Status:** done (2026-10-25).

## Files

- `predict.py`: `fetch_live` (account, 8 weekly match lists before today 00:00 UTC, details of
  the 20 most recent, all through the cache), `predict_cached` (features by `extract` and
  `features.sql`, then the ladder and SHAP), `format_prediction`.

## Rules that must not break

- **Features come from the training code.** The history helpers, a store, `extract` and
  `features.sql`, never a parallel implementation, so a live prediction can't drift from what
  the model learned. The cutoff is a UTC midnight and only weeks that have ended are fetched.
- Never print, log or return the PUUID. The output names the player by the Riot ID typed in.
- The cache (`data/raw/live.sqlite`) is under `data/` and is never committed.
- Players who didn't play in the 28 days before the cutoff get no probability: the model
  doesn't cover them (ADR 0006).

## Pitfalls

- `extract` runs its own event loop, so the network part (`fetch_live`, async) and the
  features part (`predict_cached`, sync) are separate calls.
- Don't run it while a collection uses the same key: each process has its own rate limiter,
  so together they would exceed Riot's 100 requests per 2 minutes per region.

## Tests

`tests/test_live.py`: a prediction against a fake Riot API (no week after the cutoff is
fetched, the PUUID isn't printed), the cache, a player who stopped, an unknown Riot ID, and the
CLI without models.
