from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def _prepare_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def plot_history(histories: dict[str, list[dict]], metric: str, ylabel: str, path: Path) -> None:
    _prepare_path(path)
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for model_name, rows in histories.items():
        epochs = [row["epoch"] for row in rows]
        values = [row[metric] for row in rows]
        ax.plot(epochs, values, marker="o", markersize=3, linewidth=1.5, label=model_name.upper())
    ax.set_title(f"Validation {ylabel} Curve")
    ax.set_xlabel("Epoch")
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_train_val_loss(histories: dict[str, list[dict]], path: Path) -> None:
    _prepare_path(path)
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for model_name, rows in histories.items():
        epochs = [row["epoch"] for row in rows]
        train_loss = [row["train_loss"] for row in rows]
        val_loss = [row["val_loss"] for row in rows]
        ax.plot(epochs, train_loss, marker="o", markersize=3, linewidth=1.4, label=f"{model_name.upper()} train")
        ax.plot(epochs, val_loss, marker="s", markersize=3, linewidth=1.4, label=f"{model_name.upper()} validation")
    ax.set_title("Training and Validation Loss Curves")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("NLL Loss")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_confusion_matrix(
    matrix: np.ndarray,
    labels: list[str],
    path: Path,
    title: str,
    normalize: bool = True,
) -> None:
    _prepare_path(path)
    if normalize:
        row_sum = matrix.sum(axis=1, keepdims=True)
        display_matrix = np.divide(matrix, row_sum, out=np.zeros_like(matrix, dtype=float), where=row_sum != 0)
    else:
        display_matrix = matrix

    fig_size = max(7.5, 0.45 * len(labels))
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    image = ax.imshow(display_matrix, aspect="auto")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title(title)
    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True label")
    ax.set_xticks(np.arange(len(labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=60, ha="right")
    ax.set_yticklabels(labels)

    if len(labels) <= 20:
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                value = display_matrix[i, j]
                if value > 0.01:
                    text = f"{value:.2f}" if normalize else str(int(matrix[i, j]))
                    ax.text(j, i, text, ha="center", va="center", fontsize=6)

    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_class_distribution(class_counts: dict[str, int], path: Path) -> None:
    _prepare_path(path)
    labels = list(class_counts.keys())
    values = list(class_counts.values())
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(labels, values)
    ax.set_title("Class Distribution of Name Dataset")
    ax.set_xlabel("Language")
    ax.set_ylabel("Number of names")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_metric_bars(summary_rows: list[dict], path: Path) -> None:
    _prepare_path(path)
    metrics = ["accuracy", "macro_f1"]
    models = [row["model"] for row in summary_rows]
    x = np.arange(len(models))
    width = 0.36

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for idx, metric in enumerate(metrics):
        values = [float(row[metric]) for row in summary_rows]
        ax.bar(x + (idx - 0.5) * width, values, width=width, label=metric)
    ax.set_title("Model Performance Comparison")
    ax.set_xlabel("Model")
    ax.set_ylabel("Score")
    ax.set_xticks(x)
    ax.set_xticklabels([model.upper() for model in models])
    ax.set_ylim(0, 1)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
