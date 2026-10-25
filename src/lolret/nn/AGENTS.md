# `lolret.nn`: neural nets (Phase 4b)

An MLP on the 21 tabular features and a GRU over each example's last 20 finished matches,
trained with the Phase 4a protocol and added to the same model card. Design: ADR 0004 and
ADR 0012. Config: `configs/train_nn.yaml`.

**Status:** done on run `v1` (2026-10-25); results in the README and the model card.

## Files

- `config.py`: `NNConfig` from YAML; `load_nn_config` also loads the Phase 4a config it names.
- `data.py`: `STEP_FEATURES`, `load_sequences` (`sequences.parquet` aligned to an `Examples`,
  oldest game first, plus lengths), `Scaler` (tabular design like the logistic regression,
  and per-step standardisation, fitted on training rows).
- `models.py`: `MLP` and `GRUNet`, with the same `forward(static, seq, lengths)`.
- `train.py`: `fit_net` (early stopping or a fixed epoch count), `train_kind` (seeds × folds,
  Platt on the out-of-fold mean, final nets), `train_nn_and_evaluate`, `load_nets`.

## Rules that must not break

- **The test set chooses nothing**, as in 4a: epochs, calibration and settings come from the
  player-grouped folds inside training. Settings are fixed in `configs/train_nn.yaml` before
  the test set is scored; a change after that is recorded in ADR 0012.
- **Same split, folds, bootstrap and seed as `lolret train`**, read from `configs/train.yaml`.
  `train-nn` refuses a ladder trained on other data (the examples' SHA-256 must match).
- Sequences come only from `sequences.parquet`, whose timing rules and leak guard live in the
  dataset module. Never compute a sequence feature here from raw data.
- Artifacts are `state_dict`s loaded with `weights_only=True`, plus `nn.json`. No pickles.
- torch loads only for `train-nn`, so the other commands start fast.

## Pitfalls

- A GRU needs lengths of at least 1: empty histories pass as one zero step and get a zero
  state (`GRUNet.forward`).
- Results move a little between seeds; `seeds` nets are averaged for that reason. Compare
  configurations by out-of-fold log loss, not by a single run.
- Runs on CPU in a few minutes (`v1`: ~5,600 training examples). Colab is optional
  (`notebooks/train_colab.ipynb`).

## Tests

`tests/test_nn.py`: the sequence layout, a CPU smoke test of both nets (output shape, the loss
falls), `train-nn` end to end on synthetic data (card, metrics, no identifiers), reloading,
and the refusals. The sequence leak guard is in `tests/test_dataset.py`.
