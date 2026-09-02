"""Analyze real adaptive-horizon rollout results.

Typical usage from the repository root:

python examples/libero/adaptive_horizon_analysis.py \
  --adaptive-csv runs/adaptive_horizon/adaptive_chunk_consistency/adaptive_horizon_results.csv \
  --fixed-csv runs/analysis/fixed_horizon_results.csv \
  --output runs/adaptive_horizon/analysis
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FIXED_COMPARE_METHODS = ["h6", "h8", "h10"]


def _read_csv(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV not found: {p}")
    return pd.read_csv(p)


def _normalize_adaptive(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "method" not in out.columns:
        out["method"] = "adaptive_chunk_consistency"
    out["method"] = out["method"].replace({
        "adaptive_chunk_consistency_offline": "adaptive_chunk_consistency",
        "adaptive_offline": "adaptive_chunk_consistency",
    })
    if "horizon" not in out.columns:
        out["horizon"] = out.get("selected_horizon_mean", 0)
    for col in [
        "task_success",
        "inference_count",
        "task_completion_steps",
        "episode_wall_time_ms",
        "avg_model_inference_time_ms",
        "avg_total_latency_ms",
    ]:
        if col not in out.columns:
            out[col] = 0
    if "result_source" not in out.columns:
        out["result_source"] = "real_adaptive_rollout"
    return out


def _compute_stats(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for method, sub in df.groupby("method", sort=False):
        if sub.empty:
            continue
        rows.append(
            {
                "method": method,
                "horizon": float(sub["horizon"].mean()),
                "n_episodes": int(len(sub)),
                "success_rate": float(sub["task_success"].mean()),
                "avg_inference_count": float(sub["inference_count"].mean()),
                "avg_completion_steps": float(sub["task_completion_steps"].mean()),
                "avg_wall_time_ms": float(sub["episode_wall_time_ms"].mean()),
                "avg_model_inference_ms": float(sub["avg_model_inference_time_ms"].mean()),
                "avg_total_latency_ms": float(sub["avg_total_latency_ms"].mean()),
                "result_source": str(sub["result_source"].iloc[0]) if "result_source" in sub else "unknown",
            }
        )
    return pd.DataFrame(rows)


def _collect_selected_horizons(df: pd.DataFrame) -> list[int]:
    values: list[int] = []
    if "selected_horizon_sequence" in df.columns:
        for seq in df["selected_horizon_sequence"].fillna(""):
            for item in str(seq).split(";"):
                if item.strip():
                    values.append(int(float(item)))
    if not values and "selected_horizon_mean" in df.columns:
        values = [int(round(x)) for x in df["selected_horizon_mean"].dropna().tolist()]
    if not values and "horizon" in df.columns:
        values = [int(round(x)) for x in df["horizon"].dropna().tolist()]
    return values


def _plot_bar(methods: Iterable[str], values: Iterable[float], title: str, ylabel: str, output: Path, color: str) -> None:
    methods = list(methods)
    values = list(values)
    x = np.arange(len(methods))
    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(x, values, color=color, edgecolor="black", linewidth=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=18, ha="right")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", linestyle="--", alpha=0.45)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 1.01, f"{value:.2f}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def save_plots(stats: pd.DataFrame, adaptive_df: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    methods = stats["method"].tolist()
    _plot_bar(methods, stats["success_rate"], "Adaptive vs Fixed Success Rate", "Success Rate", out_dir / "adaptive_vs_fixed_success_rate.png", "steelblue")
    _plot_bar(methods, stats["avg_inference_count"], "Adaptive vs Fixed Inference Count", "Avg Inference Count", out_dir / "adaptive_vs_fixed_inference_count.png", "darkorange")
    _plot_bar(methods, stats["avg_wall_time_ms"] / 1000.0, "Adaptive vs Fixed Episode Time", "Avg Episode Time (s)", out_dir / "adaptive_vs_fixed_episode_time.png", "seagreen")

    selected = _collect_selected_horizons(adaptive_df)
    if selected:
        counts = pd.Series(selected).value_counts().sort_index()
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.bar([str(i) for i in counts.index], counts.values, color="#6C8EBF", edgecolor="black", linewidth=0.6)
        ax.set_title("Selected Horizon Distribution", fontsize=12, fontweight="bold")
        ax.set_xlabel("Selected Horizon")
        ax.set_ylabel("Count")
        ax.grid(axis="y", linestyle="--", alpha=0.45)
        fig.tight_layout()
        fig.savefig(out_dir / "selected_horizon_distribution.png", dpi=160)
        plt.close(fig)

    if {"consistency_error_mean", "selected_horizon_mean"}.issubset(adaptive_df.columns):
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.scatter(
            adaptive_df["consistency_error_mean"],
            adaptive_df["selected_horizon_mean"],
            s=22,
            alpha=0.75,
            color="#B85450",
        )
        ax.set_title("Consistency Error vs Selected Horizon", fontsize=12, fontweight="bold")
        ax.set_xlabel("Consistency Error")
        ax.set_ylabel("Mean Selected Horizon")
        ax.grid(True, linestyle="--", alpha=0.45)
        fig.tight_layout()
        fig.savefig(out_dir / "consistency_error_vs_selected_horizon.png", dpi=160)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze adaptive horizon rollout")
    parser.add_argument("--adaptive-csv", default="runs/adaptive_horizon/adaptive_chunk_consistency/adaptive_horizon_results.csv")
    parser.add_argument("--fixed-csv", default="", help="Optional fixed_horizon_results.csv for h6/h8/h10 comparison")
    parser.add_argument("--output", default="runs/adaptive_horizon/analysis")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    adaptive = _normalize_adaptive(_read_csv(args.adaptive_csv))
    frames = []
    if args.fixed_csv:
        fixed = _read_csv(args.fixed_csv)
        if "result_source" not in fixed.columns:
            fixed["result_source"] = "real_fixed_horizon_rollout"
        fixed = fixed[fixed["method"].isin(FIXED_COMPARE_METHODS)].copy()
        frames.append(fixed)
    frames.append(adaptive)
    combined = pd.concat(frames, ignore_index=True)

    stats = _compute_stats(combined)
    stats_path = out_dir / "adaptive_horizon_stats.csv"
    stats.to_csv(stats_path, index=False)
    adaptive.to_csv(out_dir / "adaptive_horizon_results_normalized.csv", index=False)
    save_plots(stats, adaptive, out_dir)

    print(stats.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"Saved stats and plots to {out_dir.resolve()}")


if __name__ == "__main__":
    main()
