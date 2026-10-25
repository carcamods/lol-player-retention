# 0011: Forward test at the 2026-10-22 cutoff, frozen by hash

**Status:** Accepted, 2026-10-25

## Context

ADR 0006 planned a forward test: predict for every eligible player at a recent cutoff, wait 28
days, then score the predictions on outcomes that hadn't happened when they were made. Two more
reasons make it the next step after Phase 4a:

- The 4a test set (1,104 held-out players, 200 churners) has now been read several times: for
  the ladder (ADR 0008) and for the break-feature round (ADR 0010). Each further decision taken
  on it overfits it a little. The forward test is a fresh set nobody has seen.
- It is bigger. About 3,700 players are eligible at the forward cutoff, roughly three times the
  4a test set, so the intervals shrink from about ±0.043 to about ±0.025 PR-AUC. A learning
  curve on `v1` showed that doubling the players would buy less: about +0.01 PR-AUC for the
  model and ±0.030 intervals, for another ~35 hours of collection.

## Decision

**Cutoff: 2026-10-22 00:00 UTC.** Run `v1`'s last label window ends there, and it sits on
`v1`'s weekly bucket grid, so all 8 weekly match lists the features need are already cached.
Only the details of the most recent matches before the cutoff are new (about 11-17k requests
per region, 4-6 hours). It was the newest grid point already past when the work started
(2026-10-25). Choosing it a few days back costs nothing in honesty: no response from after the
cutoff is requested until the predictions are frozen and their hash is committed (see the
guards below).

**Population: every `v1` player eligible at the cutoff** (a game in the 28 days before it,
ADR 0006), including the 4a test players. The forward model trains on all of them at earlier
cutoffs, so this tests the model on the next month, not on unseen players. That's how it
would be used: score the current player base every month. The 4a test keeps answering the
unseen-players question.

**Model: the 4a ladder retrained on every labelled `v1` example** (all players, all 3
cutoffs: 11,678 examples instead of 5,617; each label known by 2026-10-22). Same settings,
selection and Platt calibration as ADR 0008 (`configs/train.yaml`), through the same code
(`fit_ladder`).

**Freezing.** `lolret forward predict` writes every model's probability for every eligible
player to `data/forward/<name>/entries/ladder.csv`, and its SHA-256 is committed in
`configs/forward.yaml` under `entries`. The file holds PUUIDs, so it stays under `data/`; the
hash is enough to prove later that it didn't change. The code enforces the order:

| Step | Refuses to run when |
|---|---|
| `forward collect` (features) | the cutoff is in the future, or labels were already collected |
| `forward predict` | the features collection isn't complete, predictions already exist, or labels were already collected |
| `forward collect --labels` | no entry hash is committed in the config, a file doesn't match its hash, or the label window hasn't ended |
| `forward score` | a file doesn't match its hash, the labels collection isn't complete, or rebuilding the features with the labels gives different features |

Run `v1`'s store is only ever opened read-only. New responses go to two separate stores, one
per phase (`data/raw/<name>.sqlite`, `data/raw/<name>-labels.sqlite`), so the labels store not
existing shows that no outcome had been collected at freezing time.

**The question, set before freezing.** Does LightGBM beat the recency rule on these outcomes:
does the paired 95% bootstrap interval of the PR-AUC difference exclude zero? Reported as well,
without deciding anything: logistic regression against the recency rule, ROC-AUC, Brier and
reliability, and how far the numbers move from the 4a test.

**Later entries.** A model built after the freeze, such as the Phase 4b neural nets, may join
as a new entry with its own committed hash, as long as the labels collection hasn't started.
Each is reported with its freeze date, and none of them changes the question above.

**Scoring.** After 2026-11-19 00:00 UTC: `lolret forward collect --labels` (four weekly
match lists per frozen player, about 1.5 hours), then `lolret forward score`, which writes
`report.md` and `results.json` next to the predictions.

## Freezing (2026-10-25)

- Features collection: 6,048 of 6,048 players, 51,697 new requests (match details only; every
  weekly match list came from `v1`'s cache) in 5 h 51 min, 0 failures.
- Ladder trained on 11,678 examples from 4,954 players: logistic regression C = 0.03, LightGBM
  171 rounds.
- Frozen at 07:06 UTC: 3,718 eligible players, mean LightGBM churn probability 19.2%. Entry
  `ladder` SHA-256 `dccb1bef0385d95d2c7cd8e918a0f1f80cbb1ba698036f2bcc07474feae27440`, committed
  in `configs/forward.yaml`. The labels store didn't exist.

## Consequences

- New module `src/lolret/forward/` and commands `lolret forward collect | predict | score`.
  The collector's per-player loop and per-platform runner became reusable helpers;
  `extract` takes an `until` horizon; `load_examples` can keep unlabelled rows; `fit_ladder`
  is shared by `lolret train` and the forward test.
- The result can't be read before 2026-11-19, and scoring needs the owner's machine and key.
- Forward numbers aren't directly comparable with the 4a test: different month, bigger model
  training set, and players the model has seen before. The report says so.
- A negative result is reported the same way as a positive one.
