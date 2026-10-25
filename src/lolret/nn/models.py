"""The two networks. Both map (tabular features, match sequence, lengths) to a churn logit, so
one training loop serves both (ADR 0004)."""

import torch
from torch import Tensor, nn
from torch.nn.utils.rnn import pack_padded_sequence


class MLP(nn.Module):
    """Feed-forward net on the tabular features; it ignores the sequence."""

    def __init__(self, n_static: int, hidden: list[int], dropout: float) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        width = n_static
        for size in hidden:
            layers += [nn.Linear(width, size), nn.ReLU(), nn.Dropout(dropout)]
            width = size
        layers.append(nn.Linear(width, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, static: Tensor, seq: Tensor, lengths: Tensor) -> Tensor:
        out: Tensor = self.net(static).squeeze(1)
        return out


class GRUNet(nn.Module):
    """A GRU reads the recent matches oldest first; its last state joins a layer over the
    tabular features. An example with no finished match gets a zero state."""

    def __init__(
        self, n_static: int, n_step: int, hidden: int, static_hidden: int, dropout: float
    ) -> None:
        super().__init__()
        self.gru = nn.GRU(n_step, hidden, batch_first=True)
        self.static = nn.Sequential(nn.Linear(n_static, static_hidden), nn.ReLU())
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden + static_hidden, 1))

    def forward(self, static: Tensor, seq: Tensor, lengths: Tensor) -> Tensor:
        packed = pack_padded_sequence(
            seq, lengths.clamp(min=1).cpu(), batch_first=True, enforce_sorted=False
        )
        _, last = self.gru(packed)  # (1, batch, hidden), in the input order
        state = last[-1] * (lengths > 0).unsqueeze(1).to(last.dtype)
        out: Tensor = self.head(torch.cat([state, self.static(static)], dim=1)).squeeze(1)
        return out
