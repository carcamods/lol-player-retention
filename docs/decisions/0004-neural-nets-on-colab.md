# 0004: Neural nets in PyTorch, trained on Google Colab

**Status:** Accepted, 2026-10-22; dependency group and training location amended by 0012

## Context

Neural networks are part of the skill set this project should show. On tabular features,
gradient boosting usually beats neural nets, so an MLP alone would mostly confirm that. A
player's match history is naturally a sequence, though: the gaps between sessions, and
streaks of losses before a break, are exactly what aggregate features flatten.

## Decision

- Two neural models, on the same splits and metrics as the classical ones:
  - an **MLP** on the tabular features, as a like-for-like comparison with LightGBM;
  - a **GRU sequence model** over the last ~20 matches before T. Each step carries
    per-match stats, the log time-gap since the previous match and the time to T. Its
    output is combined with the static features.
- **PyTorch**, with a plain training loop. It is an optional `nn` dependency group, so the
  base install and CI stay light.
- Training runs on **Google Colab** through `notebooks/train_colab.ipynb`. That notebook is a
  thin launcher: it installs this package and calls `lolret train-nn --config ...`. All logic
  lives in `src/lolret/nn/`, and the same command runs locally on CPU.
- The package supports **Python 3.12**, because that is what Colab runs. CI tests 3.12
  and 3.13.
- Private-repo access and optional Weights & Biases logging use **Colab Secrets**, never
  values in notebook cells.
- Artifacts are a `state_dict` plus the YAML config. Seeds are fixed.

## Consequences

- At about 18k sequences × 20 steps, training takes minutes. The free Colab T4 is enough;
  paid compute only matters for large hyperparameter sweeps.
- The site reports whichever model wins, including when that's LightGBM.
- CI runs a one-epoch CPU smoke test, so neural-net code can't silently break.
