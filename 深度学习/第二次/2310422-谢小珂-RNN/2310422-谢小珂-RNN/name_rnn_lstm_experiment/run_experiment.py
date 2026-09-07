from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from name_rnn_lstm_experiment.data_utils import (  # noqa: E402
    N_LETTERS,
    NameRecord,
    NameDataset,
    dataset_summary,
    load_name_records,
    save_class_distribution,
    save_json,
    set_seed,
    stratified_split,
    collate_names,
)
from name_rnn_lstm_experiment.metrics import save_dict_rows, save_matrix_csv  # noqa: E402
from name_rnn_lstm_experiment.models import build_model  # noqa: E402
from name_rnn_lstm_experiment.plotting import (  # noqa: E402
    plot_class_distribution,
    plot_confusion_matrix,
    plot_history,
    plot_metric_bars,
    plot_train_val_loss,
)
from name_rnn_lstm_experiment.train import save_history, save_predictions, train_model  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Character-level RNN/LSTM name classification experiment")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data" / "names")
    parser.add_argument("--result-dir", type=Path, default=PROJECT_ROOT / "results")
    parser.add_argument("--seed", type=int, default=2024)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--rnn-lr", type=float, default=0.003)
    parser.add_argument("--lstm-lr", type=float, default=0.003)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--grad-clip", type=float, default=5.0)
    parser.add_argument("--lstm-layers", type=int, default=1)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--torch-threads", type=int, default=1, help="CPU threads used by PyTorch; 1 is usually faster for this small RNN task.")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--smoke-test", action="store_true", help="Use fewer samples and epochs to check the pipeline quickly.")
    return parser.parse_args()


def choose_device(device_arg: str) -> torch.device:
    if device_arg == "cpu":
        return torch.device("cpu")
    if device_arg == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested, but torch.cuda.is_available() is False.")
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def limit_per_class(records: list[NameRecord], n_per_class: int, seed: int) -> list[NameRecord]:
    import random

    rng = random.Random(seed)
    by_label: dict[int, list[NameRecord]] = {}
    for record in records:
        by_label.setdefault(record.label_id, []).append(record)
    limited: list[NameRecord] = []
    for label_id in sorted(by_label):
        items = by_label[label_id][:]
        rng.shuffle(items)
        limited.extend(items[: min(n_per_class, len(items))])
    rng.shuffle(limited)
    return limited


def save_run_config(path: Path, args: argparse.Namespace, device: torch.device, labels: list[str]) -> None:
    config = vars(args).copy()
    config["data_dir"] = str(args.data_dir)
    config["result_dir"] = str(args.result_dir)
    config["device"] = str(device)
    config["n_letters"] = N_LETTERS
    config["labels"] = labels
    save_json(path, config)


def write_report_numbers(path: Path, summary_rows: list[dict], labels: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Report-ready numbers",
        "====================",
        "",
        "Models:",
        "- RNN structure is saved in outputs/rnn_model_structure.txt",
        "- LSTM structure is saved in outputs/lstm_model_structure.txt",
        "",
        "Final validation results:",
    ]
    for row in summary_rows:
        lines.append(
            f"- {row['model'].upper()}: best_epoch={row['best_epoch']}, "
            f"val_loss={float(row['val_loss']):.4f}, "
            f"val_accuracy={float(row['accuracy']):.4f}, "
            f"macro_f1={float(row['macro_f1']):.4f}"
        )
    lines.extend(
        [
            "",
            "Figures to use in the report:",
            "- figures/loss_curve.png",
            "- figures/accuracy_curve.png",
            "- figures/rnn_confusion_matrix.png",
            "- figures/lstm_confusion_matrix.png",
            "- figures/model_comparison.png",
            "",
            "Label order used by the confusion matrices:",
            ", ".join(labels),
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.smoke_test:
        args.epochs = min(args.epochs, 3)
        args.patience = min(args.patience, 2)

    if args.torch_threads > 0:
        torch.set_num_threads(args.torch_threads)

    result_dir = args.result_dir
    output_dir = result_dir / "outputs"
    figure_dir = result_dir / "figures"
    checkpoint_dir = result_dir / "checkpoints"
    for path in [output_dir, figure_dir, checkpoint_dir]:
        path.mkdir(parents=True, exist_ok=True)

    device = choose_device(args.device)
    set_seed(args.seed, use_cuda=device.type == "cuda")

    records, labels = load_name_records(args.data_dir)
    if args.smoke_test:
        records = limit_per_class(records, n_per_class=80, seed=args.seed)

    train_records, val_records = stratified_split(records, val_ratio=args.val_ratio, seed=args.seed)
    train_dataset = NameDataset(train_records)
    val_dataset = NameDataset(val_records)

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate_names,
        num_workers=args.num_workers,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collate_names,
        num_workers=args.num_workers,
    )

    full_summary = dataset_summary(records, labels)
    train_summary = dataset_summary(train_records, labels)
    val_summary = dataset_summary(val_records, labels)
    save_json(output_dir / "dataset_summary.json", {"all": full_summary, "train": train_summary, "validation": val_summary})
    save_class_distribution(output_dir / "class_distribution.csv", full_summary)
    plot_class_distribution(full_summary["class_counts"], figure_dir / "class_distribution.png")
    save_run_config(output_dir / "run_config.json", args, device, labels)

    print(json.dumps({"all": full_summary, "train": train_summary, "validation": val_summary}, ensure_ascii=False, indent=2))
    print(f"Using device: {device}")

    histories: dict[str, list[dict]] = {}
    summary_rows: list[dict] = []

    experiments = [
        ("rnn", args.rnn_lr),
        ("lstm", args.lstm_lr),
    ]
    for model_name, learning_rate in experiments:
        set_seed(args.seed, use_cuda=device.type == "cuda")
        model = build_model(
            model_name=model_name,
            input_size=N_LETTERS,
            hidden_size=args.hidden_size,
            output_size=len(labels),
            lstm_layers=args.lstm_layers,
            dropout=args.dropout,
        )
        (output_dir / f"{model_name}_model_structure.txt").write_text(str(model), encoding="utf-8")
        print("\n" + "=" * 80)
        print(f"{model_name.upper()} model structure")
        print(model)
        print("=" * 80)

        result = train_model(
            model_name=model_name,
            model=model,
            train_loader=train_loader,
            val_loader=val_loader,
            labels=labels,
            device=device,
            output_dir=result_dir,
            epochs=args.epochs,
            learning_rate=learning_rate,
            weight_decay=args.weight_decay,
            grad_clip=args.grad_clip,
            patience=args.patience,
        )

        history = result["history"]
        histories[model_name] = history
        save_history(output_dir / f"{model_name}_history.csv", history)
        save_predictions(output_dir / f"{model_name}_validation_predictions.csv", result["predictions"])
        save_matrix_csv(output_dir / f"{model_name}_confusion_matrix.csv", result["matrix"], labels)
        save_dict_rows(output_dir / f"{model_name}_per_class_metrics.csv", result["per_class"])
        plot_confusion_matrix(
            result["matrix"],
            labels,
            figure_dir / f"{model_name}_confusion_matrix.png",
            title=f"{model_name.upper()} Validation Confusion Matrix",
            normalize=True,
        )

        summary_rows.append(
            {
                "model": model_name,
                "best_epoch": result["best_epoch"],
                "epochs_ran": result["epochs_ran"],
                "val_loss": result["loss"],
                "accuracy": result["accuracy"],
                "macro_precision": result["macro_precision"],
                "macro_recall": result["macro_recall"],
                "macro_f1": result["macro_f1"],
                "elapsed_seconds": result["elapsed_seconds"],
            }
        )

    save_dict_rows(output_dir / "metrics_summary.csv", summary_rows)
    plot_train_val_loss(histories, figure_dir / "loss_curve.png")
    plot_history(histories, metric="val_accuracy", ylabel="Accuracy", path=figure_dir / "accuracy_curve.png")
    plot_history(histories, metric="val_macro_f1", ylabel="Macro F1", path=figure_dir / "macro_f1_curve.png")
    plot_metric_bars(summary_rows, figure_dir / "model_comparison.png")
    write_report_numbers(output_dir / "report_numbers.txt", summary_rows, labels)

    print("\nExperiment finished. Main outputs:")
    print(f"- Figures: {figure_dir}")
    print(f"- Tables and model structures: {output_dir}")
    print(f"- Checkpoints: {checkpoint_dir}")


if __name__ == "__main__":
    main()
