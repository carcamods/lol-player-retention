# 0012: Neural nets: match sequences, CPU training, and when a net replaces LightGBM

**Status:** Accepted, 2026-10-25

## Context

ADR 0004 planned an MLP and a GRU in PyTorch, trained on Colab, with torch as an optional
dependency group. Building them on run `v1` showed three things that shape the details:

- The training set is small (5,617 examples, 1,013 churned). A GRU over 20 matches trains in
  about a minute per setting on a laptop CPU, so Colab isn't needed at this size.
- Strict type checking and the CI smoke test both import torch, so an optional group would
  make `mypy` and `pytest` fail on a default install.
- The 4a test set has been read several times (ADR 0011). What counts as a win for a net is
  written here before any net is scored on it.

## Decision

**Sequence data.** `src/lolret/dataset/sequences.sql` lists, for every (player, cutoff), the
20 most recent games that ended at or before the cutoff: the same timing rule as the match
features (ADR 0006). `lolret build` writes it to `sequences.parquet`. The leak guard in
`tests/test_dataset.py` covers it too; an injected one-day leak failed it on all 5 seeds.

**Inputs per game (21):** log hours before the cutoff, log gap since the previous game (and a
flag when unknown), duration, result, log kills, deaths and assists, remake, surrender, queue
(ranked solo, flex, ARAM, other), role (five, or none), and whether it was the same champion
as the previous game. The tabular branch gets the 21 features, prepared like the logistic
regression's.

**Models.**
- MLP on the tabular features.
- GRU over the games, oldest first; its last state joins a layer over the tabular features.
- The average of LightGBM's and the GRU's calibrated probabilities.

**Protocol: the same as 4a** (ADR 0008). Same split, folds, bootstrap and seed. On each fold,
a net early-stops on the validation log loss; 5 independently initialised nets are averaged;
their out-of-fold predictions fit Platt scaling; the final nets train on the whole training
set for the mean stopping epoch. Settings were chosen by out-of-fold log loss inside training
(table below), never by the test set.

**Settings** (`configs/train_nn.yaml`), chosen by out-of-fold log loss over the 4a folds, 2
seeds per setting, with the test set never loaded:

| Net | Setting | OOF log loss | OOF PR-AUC |
|---|---|---|---|
| LightGBM (reference) | as in 4a | 0.3617 | 0.484 |
| MLP | 64-32, dropout 0.2, weight decay 1e-4 | 0.3650 | 0.470 |
| MLP | 32 | 0.3635 | 0.477 |
| MLP | **128-64, dropout 0.4** (weight decay 1e-4 or 1e-3) | **0.3629** | 0.474 |
| GRU | 32, dropout 0.2, weight decay 1e-4 | 0.3599 | 0.488 |
| GRU | **32, dropout 0.4, weight decay 1e-3** | **0.3599** | 0.489 |
| GRU | 16 | 0.3601 | 0.490 |
| GRU | 64, dropout 0.4 | 0.3599 | 0.485 |
| GRU | learning rate 3e-4 (with or without more regularisation) | 0.3602-0.3603 | 0.485 |

The GRU settings tie within noise; the more regularised one was kept, and both nets share
dropout 0.4 and weight decay 1e-3. Learning rate 1e-3, batch 256, up to 200 epochs with
patience 15.

**Dependencies.** torch installs by default (`default-groups`), from PyTorch's CPU wheel
index, which is a fraction of the CUDA build's size. This amends ADR 0004's optional group.
Colab stays possible through `notebooks/train_colab.ipynb`.

**The rule, written before the nets were scored on the test set:**

1. A net, or the LightGBM + GRU average, replaces LightGBM as the headline model only if the
   paired 95% bootstrap interval of its PR-AUC difference from LightGBM excludes zero.
   Otherwise LightGBM stays: it is simpler, faster and explained with SHAP.
2. All three are reported either way, against the recency rule and against LightGBM.
3. The settings in `configs/train_nn.yaml` are fixed before the first test evaluation. If they
   change after it, this ADR records why, and the first result stays reported.
4. The GRU and the average enter the forward test (ADR 0011) as later entries whatever their
   result here, so fresh outcomes judge them too.

## Consequences

- New module `src/lolret/nn/`, command `lolret train-nn` (after `lolret train`), and a
  `sequences` table in the dataset.
- The model card shows the nets next to the classical models, with a section comparing them
  with LightGBM.
- CI installs torch on every run (about 200 MB, cached).
