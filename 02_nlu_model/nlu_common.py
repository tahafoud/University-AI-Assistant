"""Shared pieces: preprocessing, char vocabulary/encoding, the CNN-BiLSTM model."""
import json
from pathlib import Path
from typing import Dict, List

import torch
import torch.nn as nn

from arabic_text import clean_arabic_text

PAD, UNK = 0, 1
MAX_LEN = 64


def preprocess(text: str) -> str:
    return clean_arabic_text(text, level="nlp")


def build_vocab(texts: List[str], min_freq: int = 1) -> Dict[str, int]:
    freq: Dict[str, int] = {}
    for t in texts:
        for ch in preprocess(t):
            freq[ch] = freq.get(ch, 0) + 1
    vocab = {"<pad>": PAD, "<unk>": UNK}
    for ch, c in sorted(freq.items()):
        if c >= min_freq:
            vocab[ch] = len(vocab)
    return vocab


def encode(text: str, vocab: Dict[str, int], max_len: int = MAX_LEN) -> List[int]:
    ids = [vocab.get(ch, UNK) for ch in preprocess(text)][:max_len]
    return ids + [PAD] * (max_len - len(ids))


class CNNBiLSTM(nn.Module):
    """
    chars -> Embedding -> multi-scale 1D-CNN (k=3,5: local char n-grams)
          -> BiLSTM (sequence context both directions)
          -> masked max-pool + masked mean-pool -> MLP -> logits
    Masking is built from the input ids, so the exported ONNX graph takes ONE
    input (input_ids) and needs no pack_padded_sequence (ONNX-unfriendly).
    """

    def __init__(self, vocab_size: int, num_classes: int, emb_dim: int = 64,
                 conv_ch: int = 64, kernels=(3, 5), hidden: int = 96,
                 dropout: float = 0.35):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, emb_dim, padding_idx=PAD)
        self.convs = nn.ModuleList(
            [nn.Conv1d(emb_dim, conv_ch, k, padding=k // 2) for k in kernels])
        self.drop = nn.Dropout(dropout)
        self.lstm = nn.LSTM(conv_ch * len(kernels), hidden,
                            batch_first=True, bidirectional=True)
        self.head = nn.Sequential(
            nn.Linear(hidden * 4, 128), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(128, num_classes))

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        mask = (ids != PAD).unsqueeze(-1).to(torch.float32)      # (B, L, 1)
        x = self.emb(ids).transpose(1, 2)                         # (B, E, L)
        x = torch.cat([torch.relu(c(x)) for c in self.convs], 1)  # (B, C, L)
        x = self.drop(x.transpose(1, 2))                          # (B, L, C)
        out, _ = self.lstm(x)                                     # (B, L, 2H)
        out = out * mask
        mx = (out + (mask - 1.0) * 1e4).max(dim=1).values
        mean = out.sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
        return self.head(self.drop(torch.cat([mx, mean], dim=1)))


def save_json(obj, path: Path):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
