from __future__ import annotations

import copy
import csv
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from .metrics import classification_metrics, confusion_matrix, per_class_metrics


def save_history(path: Path, history: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(history[0].keys()))
        writer.writeheader()
        writer.writerows(history)


def save_predictions(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["name", "true_label", "pred_label", "correct", "confidence"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    grad_clip: float,
) -> float:
    model.train()
    total_loss = 0.0
    total_examples = 0

    for batch in loader:
        x = batch["x"].to(device)
        y = batch["y"].to(device)
        lengths = batch["lengths"].to(device)

        optimizer.zero_grad(set_to_none=True)
        output = model(x, lengths)
        loss = criterion(output, y)
        loss.backward()
        if grad_clip > 0:
            nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
        optimizer.step()

        batch_size = y.size(0)
        total_loss += loss.item() * batch_size
        total_examples += batch_size

    return total_loss / max(1, total_examples)


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    labels: list[str],
) -> dict:
    model.eval()
    total_loss = 0.0
    total_examples = 0
    correct = 0
    y_true: list[int] = []
    y_pred: list[int] = []
    pred_rows: list[dict] = []

    for batch in loader:
        x = batch["x"].to(device)
        y = batch["y"].to(device)
        lengths = batch["lengths"].to(device)

        output = model(x, lengths)
        loss = criterion(output, y)
        prob = output.exp()
        confidence, pred = prob.max(dim=1)

        batch_size = y.size(0)
        total_loss += loss.item() * batch_size
        total_examples += batch_size
        correct += int((pred == y).sum().item())
        y_true.extend(y.cpu().tolist())
        y_pred.extend(pred.cpu().tolist())

        for idx in range(batch_size):
            true_id = int(y[idx].item())
            pred_id = int(pred[idx].item())
            pred_rows.append(
                {
                    "name": batch["names"][idx],
                    "true_label": labels[true_id],
                    "pred_label": labels[pred_id],
                    "correct": int(true_id == pred_id),
                    "confidence": float(confidence[idx].item()),
                }
            )

    matrix = confusion_matrix(y_true, y_pred, len(labels))
    metric_values = classification_metrics(matrix)
    metric_values.update(
        {
            "loss": total_loss / max(1, total_examples),
            "accuracy": correct / max(1, total_examples),
            "matrix": matrix,
            "predictions": pred_rows,
            "per_class": per_class_metrics(matrix, labels),
        }
    )
    return metric_values


def train_model(
    model_name: str,
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    labels: list[str],
    device: torch.device,
    output_dir: Path,
    epochs: int,
    learning_rate: float,
    weight_decay: float,
    grad_clip: float,
    patience: int,
) -> dict:
    criterion = nn.NLLLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    model = model.to(device)

    history: list[dict] = []
    best_state = copy.deepcopy(model.state_dict())
    best_val_loss = float("inf")
    best_epoch = 0
    epochs_without_improvement = 0
    start_time = time.time()

    for epoch in range(1, epochs + 1):
        train_loss = train_one_epoch(model, train_loader, criterion, optimizer, device, grad_clip)
        val_result = evaluate(model, val_loader, criterion, device, labels)
        row = {
            "epoch": epoch,
            "train_loss": train_loss,
            "val_loss": val_result["loss"],
            "val_accuracy": val_result["accuracy"],
            "val_macro_f1": val_result["macro_f1"],
        }
        history.append(row)

        print(
            f"[{model_name.upper()}] epoch {epoch:03d}/{epochs} | "
            f"train_loss={train_loss:.4f} | val_loss={row['val_loss']:.4f} | "
            f"val_acc={row['val_accuracy']:.4f} | macro_f1={row['val_macro_f1']:.4f}"
        )

        if row["val_loss"] < best_val_loss - 1e-6:
            best_val_loss = row["val_loss"]
            best_state = copy.deepcopy(model.state_dict())
            best_epoch = epoch
            epochs_without_improvement = 0
            torch.save(
                {
                    "model_name": model_name,
                    "epoch": epoch,
                    "model_state": best_state,
                    "labels": labels,
                    "history": history,
                },
                output_dir / "checkpoints" / f"best_{model_name}.pt",
            )
        else:
            epochs_without_improvement += 1

        if patience > 0 and epochs_without_improvement >= patience:
            print(f"[{model_name.upper()}] early stopped at epoch {epoch}; best epoch was {best_epoch}.")
            break

    elapsed = time.time() - start_time
    model.load_state_dict(best_state)
    final_result = evaluate(model, val_loader, criterion, device, labels)
    final_result.update(
        {
            "model": model_name,
            "best_epoch": best_epoch,
            "epochs_ran": len(history),
            "elapsed_seconds": elapsed,
            "history": history,
            "state_dict": best_state,
        }
    )
    return final_result
