from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


def confusion_matrix(y_true: list[int], y_pred: list[int], n_classes: int) -> np.ndarray:
    matrix = np.zeros((n_classes, n_classes), dtype=np.int64)
    for truth, pred in zip(y_true, y_pred):
        matrix[int(truth), int(pred)] += 1
    return matrix


def classification_metrics(matrix: np.ndarray) -> dict:
    total = int(matrix.sum())
    correct = int(np.trace(matrix))
    accuracy = correct / total if total else 0.0

    precision_values = []
    recall_values = []
    f1_values = []
    for class_id in range(matrix.shape[0]):
        tp = float(matrix[class_id, class_id])
        fp = float(matrix[:, class_id].sum() - matrix[class_id, class_id])
        fn = float(matrix[class_id, :].sum() - matrix[class_id, class_id])
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        precision_values.append(precision)
        recall_values.append(recall)
        f1_values.append(f1)

    return {
        "accuracy": accuracy,
        "macro_precision": float(np.mean(precision_values)),
        "macro_recall": float(np.mean(recall_values)),
        "macro_f1": float(np.mean(f1_values)),
    }


def per_class_metrics(matrix: np.ndarray, labels: list[str]) -> list[dict]:
    rows = []
    for class_id, label in enumerate(labels):
        tp = float(matrix[class_id, class_id])
        fp = float(matrix[:, class_id].sum() - matrix[class_id, class_id])
        fn = float(matrix[class_id, :].sum() - matrix[class_id, class_id])
        support = int(matrix[class_id, :].sum())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        rows.append(
            {
                "label": label,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": support,
            }
        )
    return rows


def save_matrix_csv(path: Path, matrix: np.ndarray, labels: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["true\\pred", *labels])
        for label, row in zip(labels, matrix.tolist()):
            writer.writerow([label, *row])


def save_dict_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
