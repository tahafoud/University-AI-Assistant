"""Train the CNN-BiLSTM intent classifier.   python train.py --epochs 80"""
import argparse
import random
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from data import build_splits
from nlu_common import CNNBiLSTM, MAX_LEN, build_vocab, encode, save_json


def to_tensors(pairs, vocab):
    x = torch.tensor([encode(t, vocab) for t, _ in pairs], dtype=torch.long)
    y = torch.tensor([l for _, l in pairs], dtype=torch.long)
    return x, y


@torch.no_grad()
def evaluate(model, x, y, crit):
    model.eval()
    logits = model(x)
    return crit(logits, y).item(), (logits.argmax(1) == y).float().mean().item(), logits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="artifacts")
    a = ap.parse_args()

    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    out = Path(a.out); out.mkdir(exist_ok=True)

    labels, train, val = build_splits(seed=a.seed)
    vocab = build_vocab([t for t, _ in train])
    print(f"classes={len(labels)} train={len(train)} val={len(val)} vocab={len(vocab)}")

    xtr, ytr = to_tensors(train, vocab)
    xva, yva = to_tensors(val, vocab)
    loader = DataLoader(TensorDataset(xtr, ytr), batch_size=a.batch, shuffle=True)

    cfg = dict(vocab_size=len(vocab), num_classes=len(labels), emb_dim=64,
               conv_ch=64, kernels=[3, 5], hidden=96, dropout=0.35, max_len=MAX_LEN)
    model = CNNBiLSTM(**{k: v for k, v in cfg.items() if k != "max_len"})
    print("params:", sum(p.numel() for p in model.parameters()))

    crit = nn.CrossEntropyLoss(label_smoothing=0.05)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-2)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=5)

    best_acc, best_loss, bad = -1.0, 9e9, 0
    for ep in range(1, a.epochs + 1):
        model.train()
        tot = 0.0
        for xb, yb in loader:
            opt.zero_grad()
            loss = crit(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item() * len(xb)
        vl, va, _ = evaluate(model, xva, yva, crit)
        sched.step(vl)
        print(f"ep {ep:3d}  train_loss {tot/len(xtr):.4f}  val_loss {vl:.4f}  val_acc {va:.3f}")
        if va > best_acc or (va == best_acc and vl < best_loss):
            best_acc, best_loss, bad = va, vl, 0
            torch.save(model.state_dict(), out / "model.pt")
        else:
            bad += 1
            if bad >= a.patience:
                print("early stop"); break

    model.load_state_dict(torch.load(out / "model.pt"))
    _, acc, logits = evaluate(model, xva, yva, crit)
    pred = logits.argmax(1)
    print(f"\nBEST val accuracy: {acc:.3f}\n")
    print(f"{'intent':26s}  prec   rec    f1   n")
    for i, name in enumerate(labels):
        tp = ((pred == i) & (yva == i)).sum().item()
        fp = ((pred == i) & (yva != i)).sum().item()
        fn = ((pred != i) & (yva == i)).sum().item()
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        print(f"{name:26s}  {p:.2f}   {r:.2f}   {f:.2f}  {(yva == i).sum().item()}")

    # Confidence threshold guidance: below it the app answers "I didn't understand"
    conf = torch.softmax(logits, 1).max(1).values
    print("\nthreshold  coverage  accuracy_on_answered")
    for th in (0.4, 0.5, 0.6, 0.7, 0.8):
        m = conf >= th
        cov = m.float().mean().item()
        ac = (pred[m] == yva[m]).float().mean().item() if m.any() else float("nan")
        print(f"  {th:.1f}       {cov:.2f}      {ac:.3f}")

    save_json(vocab, out / "vocab.json")
    save_json(labels, out / "labels.json")
    save_json(cfg, out / "config.json")
    print(f"\nSaved to {out}/ (model.pt, vocab.json, labels.json, config.json)")


if __name__ == "__main__":
    main()
