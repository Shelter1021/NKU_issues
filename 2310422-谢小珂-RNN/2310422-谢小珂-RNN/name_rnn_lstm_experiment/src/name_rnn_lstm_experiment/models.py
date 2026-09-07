from __future__ import annotations

import torch
import torch.nn as nn
from torch.nn.utils.rnn import pack_padded_sequence


class CharRNN(nn.Module):
    """Teacher-style RNN baseline for name classification.

    The layer names intentionally follow the tutorial: rnn -> h2o -> softmax.
    """

    def __init__(self, input_size: int, hidden_size: int, output_size: int):
        super().__init__()
        self.rnn = nn.RNN(input_size, hidden_size)
        self.h2o = nn.Linear(hidden_size, output_size)
        self.softmax = nn.LogSoftmax(dim=1)

    def forward(self, line_tensor: torch.Tensor, lengths: torch.Tensor | None = None) -> torch.Tensor:
        if lengths is None:
            _, hidden = self.rnn(line_tensor)
        else:
            packed = pack_padded_sequence(
                line_tensor,
                lengths.cpu(),
                enforce_sorted=False,
            )
            _, hidden = self.rnn(packed)
        output = self.h2o(hidden[-1])
        output = self.softmax(output)
        return output


class CharLSTM(nn.Module):
    """LSTM classifier implemented for the comparison experiment."""

    def __init__(
        self,
        input_size: int,
        hidden_size: int,
        output_size: int,
        num_layers: int = 1,
        dropout: float = 0.2,
    ):
        super().__init__()
        lstm_dropout = dropout if num_layers > 1 else 0.0
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=lstm_dropout,
        )
        self.dropout = nn.Dropout(dropout)
        self.h2o = nn.Linear(hidden_size, output_size)
        self.softmax = nn.LogSoftmax(dim=1)

    def forward(self, line_tensor: torch.Tensor, lengths: torch.Tensor | None = None) -> torch.Tensor:
        if lengths is None:
            _, (hidden, _) = self.lstm(line_tensor)
        else:
            packed = pack_padded_sequence(
                line_tensor,
                lengths.cpu(),
                enforce_sorted=False,
            )
            _, (hidden, _) = self.lstm(packed)
        final_hidden = self.dropout(hidden[-1])
        output = self.h2o(final_hidden)
        output = self.softmax(output)
        return output


def build_model(
    model_name: str,
    input_size: int,
    hidden_size: int,
    output_size: int,
    lstm_layers: int = 1,
    dropout: float = 0.2,
) -> nn.Module:
    if model_name == "rnn":
        return CharRNN(input_size, hidden_size, output_size)
    if model_name == "lstm":
        return CharLSTM(input_size, hidden_size, output_size, lstm_layers, dropout)
    raise ValueError(f"Unknown model name: {model_name}")
