import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Create summary figures/tables for the report.")
    parser.add_argument("--output_dir", type=str, default="outputs")
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    summary_path = output_dir / "summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError(f"Cannot find {summary_path}. Train models first.")

    df = pd.read_csv(summary_path)
    df = df.sort_values("best_val_acc", ascending=False)

    fig_path = output_dir / "model_comparison.png"
    plt.figure(figsize=(9, 4.8))
    names = df["model"].tolist()
    x = range(len(names))
    plt.bar(x, df["best_val_acc"] * 100, label="Best Val Acc")
    plt.plot(x, df["test_acc"] * 100, marker="o", label="Test Acc")
    plt.xticks(list(x), names, rotation=25, ha="right")
    plt.ylabel("Accuracy (%)")
    plt.title("CIFAR-10 Model Comparison")
    plt.legend()
    plt.grid(True, axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(fig_path, dpi=300)
    plt.close()

    md_path = output_dir / "report_table.md"
    table = df[["model", "params", "best_epoch", "best_val_acc", "best_val_loss", "test_acc", "test_loss", "total_time"]].copy()
    table["best_val_acc"] = (table["best_val_acc"] * 100).map(lambda v: f"{v:.2f}%")
    table["test_acc"] = (table["test_acc"] * 100).map(lambda v: f"{v:.2f}%")
    headers = list(table.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in table.iterrows():
        lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Saved {fig_path}")
    print(f"Saved {md_path}")


if __name__ == "__main__":
    main()
