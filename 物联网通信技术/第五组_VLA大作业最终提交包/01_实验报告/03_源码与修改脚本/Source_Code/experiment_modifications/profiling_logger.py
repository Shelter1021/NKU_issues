"""CSV profiling helper for fixed-horizon StreamingVLA experiments.

This module mirrors the profiling fields used by the modified
``streamingvla.py`` runner. It can be imported by future runners, or used as
the reference implementation for how each per-episode row should be written.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, Optional


PROFILING_FIELDS = [
    "method",
    "horizon",
    "task_id",
    "episode_id",
    "task_success",
    "inference_count",
    "task_completion_steps",
    "episode_wall_time_ms",
    "avg_model_inference_time_ms",
    "avg_total_latency_ms",
]


class ProfilingLogger:
    """Write per-episode profiling records to a UTF-8 CSV file."""

    def __init__(self, csv_path: str | Path, fieldnames: Optional[Iterable[str]] = None) -> None:
        self.csv_path = Path(csv_path)
        self.fieldnames = list(fieldnames or PROFILING_FIELDS)
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.csv_path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.fieldnames)
        self._writer.writeheader()

    def write_episode(
        self,
        *,
        method: str,
        horizon: int,
        task_id: int,
        episode_id: int,
        task_success: bool,
        inference_count: int,
        task_completion_steps: int,
        episode_wall_time_ms: float,
        avg_model_inference_time_ms: float,
        avg_total_latency_ms: float,
    ) -> None:
        row: Dict[str, object] = {
            "method": method,
            "horizon": horizon,
            "task_id": task_id,
            "episode_id": episode_id,
            "task_success": int(task_success),
            "inference_count": inference_count,
            "task_completion_steps": task_completion_steps,
            "episode_wall_time_ms": round(episode_wall_time_ms, 3),
            "avg_model_inference_time_ms": round(avg_model_inference_time_ms, 3),
            "avg_total_latency_ms": round(avg_total_latency_ms, 3),
        }
        self._writer.writerow(row)
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "ProfilingLogger":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
