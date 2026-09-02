"""
latency_analysis.py
读取 fixed_horizon 实验的 results.csv，生成作业要求的 4 张对比图，
并输出汇总统计表。

用法：
    # 自动搜索 runs/fixed_horizon/*/results.csv
    python examples/libero/latency_analysis.py

    # 指定输出目录
    python examples/libero/latency_analysis.py --input runs/fixed_horizon --output runs/analysis

    # 只分析特定文件（以逗号分隔）
    python examples/libero/latency_analysis.py \
        --csv-files runs/fixed_horizon/baseline/results.csv,runs/fixed_horizon/h4/results.csv
"""

import argparse
import glob
import pathlib
import sys
from typing import List

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# Horizon 显示顺序（x 轴）
HORIZON_ORDER = ["baseline", "h1", "h2", "h4", "h8", "h10", "h16"]

# 图表样式
STYLE = {
    "figure.figsize": (8, 5),
    "axes.grid": True,
    "grid.linestyle": "--",
    "grid.alpha": 0.5,
    "font.size": 11,
}


def load_csv_files(csv_paths: List[str]) -> pd.DataFrame:
    dfs = []
    for p in csv_paths:
        if not pathlib.Path(p).exists():
            print(f"[warn] 文件不存在，跳过: {p}")
            continue
        df = pd.read_csv(p)
        dfs.append(df)
    if not dfs:
        sys.exit("[error] 没有找到任何有效的 CSV 文件，请检查路径")
    combined = pd.concat(dfs, ignore_index=True)
    print(f"[info] 加载 {len(dfs)} 个文件，共 {len(combined)} 行 episode 数据")
    return combined


def get_ordered_methods(df: pd.DataFrame) -> List[str]:
    present = df["method"].unique().tolist()
    ordered = [m for m in HORIZON_ORDER if m in present]
    extra = [m for m in present if m not in ordered]
    return ordered + sorted(extra)


def compute_stats(df: pd.DataFrame, methods: List[str]) -> pd.DataFrame:
    rows = []
    for m in methods:
        sub = df[df["method"] == m]
        if sub.empty:
            continue
        horizon = sub["horizon"].iloc[0]
        n = len(sub)
        n_success = sub["task_success"].sum()
        rows.append({
            "method": m,
            "horizon": horizon,
            "n_episodes": n,
            "success_rate": n_success / n if n > 0 else 0.0,
            "avg_inference_count": sub["inference_count"].mean(),
            "avg_completion_steps": sub["task_completion_steps"].mean(),
            "avg_wall_time_ms": sub["episode_wall_time_ms"].mean(),
            "avg_model_inference_ms": sub["avg_model_inference_time_ms"].mean(),
            "avg_total_latency_ms": sub["avg_total_latency_ms"].mean(),
        })
    return pd.DataFrame(rows)


def plot_bar(methods, values, title, ylabel, output_path, color="steelblue", fmt=".2f"):
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots()
        x = np.arange(len(methods))
        bars = ax.bar(x, values, color=color, edgecolor="black", linewidth=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(methods, rotation=20, ha="right")
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Method (Horizon)")
        # 数值标注
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() * 1.01,
                f"{val:{fmt}}",
                ha="center", va="bottom", fontsize=9,
            )
        fig.tight_layout()
        fig.savefig(output_path, dpi=150)
        plt.close(fig)
    print(f"[info] 已保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Horizon Latency Analysis")
    parser.add_argument(
        "--input",
        default="runs/fixed_horizon",
        help="包含各 horizon 子目录的根目录（每个子目录下应有 results.csv）",
    )
    parser.add_argument(
        "--csv-files",
        default="",
        help="直接指定 CSV 文件路径，逗号分隔（优先于 --input）",
    )
    parser.add_argument(
        "--output",
        default="runs/analysis",
        help="图表和汇总表的输出目录",
    )
    parser.add_argument(
        "--merged-csv",
        default="fixed_horizon_results.csv",
        help="合并后 CSV 的文件名（保存在 --output 目录下）",
    )
    args = parser.parse_args()

    out_dir = pathlib.Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 收集 CSV 路径
    if args.csv_files:
        csv_paths = [p.strip() for p in args.csv_files.split(",")]
    else:
        pattern = str(pathlib.Path(args.input) / "*" / "results.csv")
        csv_paths = sorted(glob.glob(pattern))
        if not csv_paths:
            sys.exit(f"[error] 在 {pattern} 下未找到任何 results.csv，请确认路径或使用 --csv-files")

    df = load_csv_files(csv_paths)

    # 保存合并 CSV
    merged_path = out_dir / args.merged_csv
    df.to_csv(merged_path, index=False)
    print(f"[info] 合并 CSV 已保存: {merged_path}")

    methods = get_ordered_methods(df)
    stats = compute_stats(df, methods)

    # 打印汇总表
    print("\n" + "=" * 80)
    print("汇总统计表")
    print("=" * 80)
    print(stats.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("=" * 80)

    # 保存汇总表
    stats_path = out_dir / "stats_table.csv"
    stats.to_csv(stats_path, index=False)
    print(f"[info] 汇总表已保存: {stats_path}")

    method_labels = stats["method"].tolist()

    # ---- 图 1：成功率 ----
    plot_bar(
        method_labels,
        stats["success_rate"].tolist(),
        title="Horizon vs Task Success Rate",
        ylabel="Success Rate",
        output_path=out_dir / "horizon_vs_success_rate.png",
        color="steelblue",
        fmt=".3f",
    )

    # ---- 图 2：推理次数 ----
    plot_bar(
        method_labels,
        stats["avg_inference_count"].tolist(),
        title="Horizon vs Average Inference Count per Episode",
        ylabel="Avg Inference Count",
        output_path=out_dir / "horizon_vs_inference_count.png",
        color="darkorange",
        fmt=".1f",
    )

    # ---- 图 3：完成步数 / Episode 时间（双轴） ----
    with plt.rc_context(STYLE):
        fig, ax1 = plt.subplots()
        x = np.arange(len(method_labels))
        w = 0.35
        b1 = ax1.bar(x - w / 2, stats["avg_completion_steps"].tolist(), w,
                     label="Avg Completion Steps", color="seagreen", edgecolor="black", linewidth=0.6)
        ax2 = ax1.twinx()
        b2 = ax2.bar(x + w / 2, (stats["avg_wall_time_ms"] / 1000).tolist(), w,
                     label="Avg Wall Time (s)", color="tomato", edgecolor="black", linewidth=0.6)
        ax1.set_xticks(x)
        ax1.set_xticklabels(method_labels, rotation=20, ha="right")
        ax1.set_ylabel("Avg Completion Steps", color="seagreen")
        ax2.set_ylabel("Avg Wall Time (s)", color="tomato")
        ax1.set_title("Horizon vs Completion Steps / Episode Time", fontsize=12, fontweight="bold")
        lines = [b1, b2]
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc="upper right")
        fig.tight_layout()
        p = out_dir / "horizon_vs_completion_steps_or_time.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
    print(f"[info] 已保存: {p}")

    # ---- 图 4：推理耗时 / 端到端时延（双轴） ----
    with plt.rc_context(STYLE):
        fig, ax1 = plt.subplots()
        x = np.arange(len(method_labels))
        w = 0.35
        b1 = ax1.bar(x - w / 2, stats["avg_model_inference_ms"].tolist(), w,
                     label="Avg Model Inference Time (ms)", color="mediumpurple", edgecolor="black", linewidth=0.6)
        ax2 = ax1.twinx()
        b2 = ax2.bar(x + w / 2, stats["avg_total_latency_ms"].tolist(), w,
                     label="Avg Total Latency (ms)", color="goldenrod", edgecolor="black", linewidth=0.6)
        ax1.set_xticks(x)
        ax1.set_xticklabels(method_labels, rotation=20, ha="right")
        ax1.set_ylabel("Model Inference Time (ms)", color="mediumpurple")
        ax2.set_ylabel("Total Latency (ms)", color="goldenrod")
        ax1.set_title("Horizon vs Model Inference Time / Total Latency", fontsize=12, fontweight="bold")
        lines = [b1, b2]
        labels = [l.get_label() for l in lines]
        ax1.legend(lines, labels, loc="upper right")
        fig.tight_layout()
        p = out_dir / "horizon_vs_model_inference_time.png"
        fig.savefig(p, dpi=150)
        plt.close(fig)
    print(f"[info] 已保存: {p}")

    print(f"\n[info] 全部完成，输出目录: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
