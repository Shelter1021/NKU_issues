#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def read_all(results_dir: Path, filename: str) -> pd.DataFrame:
    frames = []
    for path in sorted(results_dir.glob(f"*/{filename}")):
        df = pd.read_csv(path)
        df["run_dir"] = path.parent.name
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def save_bar(df: pd.DataFrame, x: str, ys: list[str], title: str, ylabel: str, out: Path) -> None:
    ax = df.set_index(x)[ys].plot(kind="bar", figsize=(12, 6))
    ax.set_title(title)
    ax.set_xlabel(x)
    ax.set_ylabel(ylabel)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(out, dpi=180)
    plt.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", default="results")
    args = p.parse_args()

    results_dir = Path(args.results_dir)
    out_dir = results_dir / "_summary"
    out_dir.mkdir(parents=True, exist_ok=True)

    insert_df = read_all(results_dir, "insert_details.csv")
    summary_df = read_all(results_dir, "workload_summary.csv")
    query_df = read_all(results_dir, "query_results.csv")

    if not insert_df.empty:
        insert_df.to_csv(out_dir / "all_insert_details.csv", index=False, encoding="utf-8-sig")
    if not summary_df.empty:
        summary_df.to_csv(out_dir / "all_workload_summary.csv", index=False, encoding="utf-8-sig")
        save_bar(
            summary_df,
            "run_name",
            ["unique_plaintexts", "unique_ciphertexts", "unique_inserted_encodings"],
            "Frequency-Hiding Effect by Workload",
            "Count",
            out_dir / "unique_counts.png",
        )
        save_bar(
            summary_df,
            "run_name",
            ["leaf_splits", "internal_splits"],
            "Split Counts by Workload",
            "Count",
            out_dir / "split_counts.png",
        )
        save_bar(
            summary_df,
            "run_name",
            ["encoding_updates", "changed_rows_total"],
            "Encoding Update Cost by Workload",
            "Count",
            out_dir / "encoding_update_cost.png",
        )

    if not query_df.empty:
        query_df.to_csv(out_dir / "all_query_results.csv", index=False, encoding="utf-8-sig")

    if not insert_df.empty:
        event_df = insert_df[
            (insert_df["leaf_split_delta"].astype(int) > 0) |
            (insert_df["internal_split_delta"].astype(int) > 0) |
            (insert_df["update_triggered"].astype(int) > 0)
        ].copy()
        event_df.to_csv(out_dir / "event_timeline.csv", index=False, encoding="utf-8-sig")

        plt.figure(figsize=(12, 6))
        for run_name, sub in insert_df.groupby("run_dir"):
            plt.plot(sub["insert_index"], sub["encoding"], marker="o", linewidth=1, label=run_name)
        plt.title("Inserted Encoding Distribution")
        plt.xlabel("Insert Index")
        plt.ylabel("Encoding")
        plt.legend(fontsize=7)
        plt.tight_layout()
        plt.savefig(out_dir / "encoding_distribution.png", dpi=180)
        plt.close()

    print(f"[analysis] summary files saved to {out_dir}")


if __name__ == "__main__":
    main()
