"""
fixed_horizon_runner.py
批量运行不同固定 horizon 的 libero 评测实验。

用法示例：
    # 全部 7 组
    python examples/libero/fixed_horizon_runner.py

    # 精简 5 组（时间不足时）
    python examples/libero/fixed_horizon_runner.py --groups baseline,h1,h4,h8,h10

    # 单组调试（1 trial）
    python examples/libero/fixed_horizon_runner.py --groups h4 --num-trials 1
"""

import argparse
import pathlib
import subprocess
import sys
import time


# -----------------------------------------------------------------------
# 实验设置
# -----------------------------------------------------------------------
HORIZON_CONFIGS = {
    "baseline": {
        "replan_steps": 10,
        "fixed_horizon_mode": False,   # 保留原始 judger 行为
        "method_name": "baseline",
    },
    "h1": {
        "replan_steps": 1,
        "fixed_horizon_mode": True,
        "method_name": "h1",
    },
    "h2": {
        "replan_steps": 2,
        "fixed_horizon_mode": True,
        "method_name": "h2",
    },
    "h4": {
        "replan_steps": 4,
        "fixed_horizon_mode": True,
        "method_name": "h4",
    },
    "h8": {
        "replan_steps": 8,
        "fixed_horizon_mode": True,
        "method_name": "h8",
    },
    "h10": {
        "replan_steps": 10,
        "fixed_horizon_mode": True,
        "method_name": "h10",
    },
    "h16": {
        "replan_steps": 16,
        "fixed_horizon_mode": True,
        "method_name": "h16",
    },
}

ALL_GROUPS = ["baseline", "h1", "h2", "h4", "h8", "h10", "h16"]
MINIMAL_GROUPS = ["baseline", "h1", "h4", "h8", "h10"]  # 时间不足时使用


def build_command(
    cfg: dict,
    base_dir: pathlib.Path,
    task_suite: str,
    num_trials: int,
    seed: int,
    host: str,
    port: int,
) -> list:
    name = cfg["method_name"]
    out_dir = base_dir / name

    # tyro parses bool flags as --flag / --no-flag, NOT --flag=True
    fixed_horizon_flag = (
        "--args.fixed-horizon-mode"
        if cfg["fixed_horizon_mode"]
        else "--no-args.fixed-horizon-mode"
    )

    cmd = [
        sys.executable,
        "examples/libero/streamingvla.py",
        f"--args.host={host}",
        f"--args.port={port}",
        f"--args.task-suite-name={task_suite}",
        f"--args.num-trials-per-task={num_trials}",
        f"--args.seed={seed}",
        f"--args.replan-steps={cfg['replan_steps']}",
        fixed_horizon_flag,
        f"--args.method-name={name}",
        f"--args.profiling-csv-path={out_dir}/results.csv",
        f"--args.video-out-path={out_dir}/videos",
        f"--args.timing-output-path={out_dir}/timing.txt",
    ]
    return cmd


def run_group(name: str, cfg: dict, args: argparse.Namespace) -> bool:
    base_dir = pathlib.Path(args.output_dir)
    out_dir = base_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_command(
        cfg,
        base_dir,
        task_suite=args.task_suite,
        num_trials=args.num_trials,
        seed=args.seed,
        host=args.host,
        port=args.port,
    )

    # 保存本次运行命令
    cmd_str = " \\\n  ".join(cmd)
    (out_dir / "command.txt").write_text(cmd_str + "\n", encoding="utf-8")

    log_path = out_dir / "log.txt"
    print(f"\n{'='*60}")
    print(f"[runner] 开始: {name}  (replan_steps={cfg['replan_steps']}, judger={not cfg['fixed_horizon_mode']})")
    print(f"[runner] 日志: {log_path}")
    print(f"{'='*60}")

    t0 = time.monotonic()
    # Stream output directly to file to avoid buffering entire long-run output in memory
    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"Command:\n{cmd_str}\n\n")
        log_file.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        proc.wait()
        returncode = proc.returncode

    elapsed = time.monotonic() - t0
    ok = returncode == 0
    status = "OK" if ok else f"FAILED (code={returncode})"
    print(f"[runner] 完成: {name}  耗时={elapsed/60:.1f} min  状态={status}")

    # 打印日志尾部到终端
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for line in lines[-10:]:
            print(f"  | {line.rstrip()}")
    except Exception:
        pass

    return ok


def main():
    parser = argparse.ArgumentParser(description="Fixed Horizon Batch Runner")
    parser.add_argument(
        "--groups",
        default=",".join(ALL_GROUPS),
        help=f"逗号分隔的实验组名，可选: {list(HORIZON_CONFIGS.keys())}",
    )
    parser.add_argument("--task-suite", default="libero_spatial")
    parser.add_argument("--num-trials", type=int, default=10, help="每个任务的 episode 数")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8192)
    parser.add_argument(
        "--output-dir",
        default="runs/fixed_horizon",
        help="结果根目录，每组在其下建子目录",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印命令，不实际运行",
    )
    args = parser.parse_args()

    selected = [g.strip() for g in args.groups.split(",") if g.strip()]
    unknown = [g for g in selected if g not in HORIZON_CONFIGS]
    if unknown:
        parser.error(f"未知 group: {unknown}，可选: {list(HORIZON_CONFIGS.keys())}")

    print(f"[runner] 任务集: {args.task_suite}")
    print(f"[runner] 每任务次数: {args.num_trials}  seed: {args.seed}")
    print(f"[runner] 输出目录: {args.output_dir}")
    print(f"[runner] 实验组: {selected}")

    results = {}
    for name in selected:
        cfg = HORIZON_CONFIGS[name]
        if args.dry_run:
            cmd = build_command(
                cfg,
                pathlib.Path(args.output_dir),
                args.task_suite,
                args.num_trials,
                args.seed,
                args.host,
                args.port,
            )
            print(f"\n[dry-run] {name}:")
            print("  " + " \\\n  ".join(cmd))
            results[name] = True
        else:
            ok = run_group(name, cfg, args)
            results[name] = ok

    print(f"\n{'='*60}")
    print("[runner] 汇总：")
    for name, ok in results.items():
        print(f"  {name:12s} {'✓' if ok else '✗'}")

    failed = [n for n, ok in results.items() if not ok]
    if failed:
        print(f"[runner] 失败组: {failed}")
        sys.exit(1)
    else:
        print("[runner] 全部完成")


if __name__ == "__main__":
    main()
