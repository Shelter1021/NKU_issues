import json
import random
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch


def set_seed(seed=2026):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = True


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


class AverageMeter:
    def __init__(self):
        self.reset()

    def reset(self):
        self.total = 0.0
        self.count = 0

    def update(self, value, n=1):
        self.total += float(value) * n
        self.count += n

    @property
    def avg(self):
        return self.total / self.count if self.count else 0.0


def accuracy(output, target):
    pred = output.argmax(dim=1)
    return pred.eq(target).float().mean().item()


def save_model_structure(model, save_path):
    save_path = Path(save_path)
    ensure_dir(save_path.parent)
    text = str(model) + "\n"
    try:
        from torchinfo import summary
        info = summary(model, input_size=(1, 3, 32, 32), verbose=0)
        text += "\n" + str(info) + "\n"
    except Exception as exc:
        text += f"\n[torchinfo summary skipped: {exc}]\n"
    save_path.write_text(text, encoding="utf-8")


def save_json(obj, save_path):
    save_path = Path(save_path)
    ensure_dir(save_path.parent)
    save_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def save_metrics_csv(history, save_path):
    save_path = Path(save_path)
    ensure_dir(save_path.parent)
    pd.DataFrame(history).to_csv(save_path, index=False, encoding="utf-8-sig")


def plot_curves(history, save_path, title):
    save_path = Path(save_path)
    ensure_dir(save_path.parent)
    df = pd.DataFrame(history)
    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    plt.plot(df["epoch"], df["train_loss"], label="Train Loss")
    plt.plot(df["epoch"], df["val_loss"], label="Val Loss")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.title(f"{title} Loss")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.subplot(1, 2, 2)
    plt.plot(df["epoch"], df["train_acc"], label="Train Acc")
    plt.plot(df["epoch"], df["val_acc"], label="Val Acc")
    plt.xlabel("Epoch")
    plt.ylabel("Accuracy")
    plt.title(f"{title} Accuracy")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(save_path, dpi=300)
    plt.close()


def update_summary(summary_path, row):
    summary_path = Path(summary_path)
    ensure_dir(summary_path.parent)
    if summary_path.exists():
        df = pd.read_csv(summary_path)
        df = df[df["model"] != row["model"]]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df = df.sort_values(by="best_val_acc", ascending=False)
    df.to_csv(summary_path, index=False, encoding="utf-8-sig")


def format_time(seconds):
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"


def current_time():
    return time.strftime("%Y-%m-%d %H:%M:%S")
