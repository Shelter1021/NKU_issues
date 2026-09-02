"""Batch runner for chunk-consistency adaptive horizon experiments.

This runner assumes the modified ``streamingvla.py`` supports
``--args.adaptive-horizon-mode``. It launches one adaptive group and writes
outputs using the same layout as the fixed-horizon runner.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import time


def build_command(args: argparse.Namespace) -> list[str]:
    out_dir = pathlib.Path(args.output_dir) / args.method_name
    return [
        sys.executable,
        "examples/libero/streamingvla.py",
        f"--args.host={args.host}",
        f"--args.port={args.port}",
        f"--args.task-suite-name={args.task_suite}",
        f"--args.num-trials-per-task={args.num_trials}",
        f"--args.seed={args.seed}",
        f"--args.replan-steps={args.initial_horizon}",
        "--args.adaptive-horizon-mode",
        "--args.fixed-horizon-mode",
        f"--args.adaptive-min-horizon={args.min_horizon}",
        f"--args.adaptive-mid-horizon={args.mid_horizon}",
        f"--args.adaptive-max-horizon={args.max_horizon}",
        f"--args.adaptive-tau-low={args.tau_low}",
        f"--args.adaptive-tau-high={args.tau_high}",
        f"--args.method-name={args.method_name}",
        f"--args.profiling-csv-path={out_dir / 'adaptive_horizon_results.csv'}",
        f"--args.video-out-path={out_dir / 'videos'}",
        f"--args.timing-output-path={out_dir / 'timing.txt'}",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Adaptive Horizon Batch Runner")
    parser.add_argument("--task-suite", default="libero_spatial")
    parser.add_argument("--num-trials", type=int, default=10)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8192)
    parser.add_argument("--output-dir", default="runs/adaptive_horizon")
    parser.add_argument("--method-name", default="adaptive_chunk_consistency")
    parser.add_argument("--initial-horizon", type=int, default=8)
    parser.add_argument("--min-horizon", type=int, default=6)
    parser.add_argument("--mid-horizon", type=int, default=8)
    parser.add_argument("--max-horizon", type=int, default=10)
    parser.add_argument("--tau-low", type=float, default=0.03)
    parser.add_argument("--tau-high", type=float, default=0.07)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    out_dir = pathlib.Path(args.output_dir) / args.method_name
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_command(args)
    cmd_str = " \\\n  ".join(str(x) for x in cmd)
    (out_dir / "command.txt").write_text(cmd_str + "\n", encoding="utf-8")

    print("[adaptive-runner] command:")
    print(cmd_str)
    if args.dry_run:
        return

    t0 = time.monotonic()
    log_path = out_dir / "log.txt"
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"Command:\n{cmd_str}\n\n")
        log_file.flush()
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
        proc.wait()
        code = proc.returncode

    elapsed = (time.monotonic() - t0) / 60
    print(f"[adaptive-runner] finished code={code}, elapsed={elapsed:.1f} min")
    if code != 0:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
