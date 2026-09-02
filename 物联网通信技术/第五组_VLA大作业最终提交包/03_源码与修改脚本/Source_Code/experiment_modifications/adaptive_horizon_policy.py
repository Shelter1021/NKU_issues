"""Adaptive horizon policy based on action-chunk consistency.

The policy is intentionally lightweight: it does not retrain the VLA model.
It only changes the number of actions executed before the next observation.

Primary signal:
    Compare the overlapping part of two consecutive predicted action chunks.
    Stable overlap -> longer horizon. Unstable overlap -> shorter horizon.

Fallback signal:
    If the serving stack does not expose full action chunks, use variation in
    recently executed actions as a proxy. This keeps the runner usable, while
    the CSV marks the signal source so the result can be interpreted honestly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

import numpy as np


@dataclass
class AdaptiveDecision:
    selected_horizon: int
    consistency_error: float
    signal_source: str
    gripper_changed: bool = False


class ChunkConsistencyAdaptiveHorizon:
    """Three-level adaptive horizon policy.

    Candidate horizons are limited to 6, 8, and 10 because the provided
    StreamingVLA checkpoint uses action_horizon=10, and the fixed-horizon
    results show h1/h2/h4 are not stable on libero_spatial.
    """

    def __init__(
        self,
        min_horizon: int = 6,
        mid_horizon: int = 8,
        max_horizon: int = 10,
        tau_low: float = 0.03,
        tau_high: float = 0.07,
        action_dims: int = 6,
        gripper_threshold: float = 0.25,
    ) -> None:
        if not (min_horizon <= mid_horizon <= max_horizon):
            raise ValueError("Expected min_horizon <= mid_horizon <= max_horizon")
        self.min_horizon = min_horizon
        self.mid_horizon = mid_horizon
        self.max_horizon = max_horizon
        self.tau_low = tau_low
        self.tau_high = tau_high
        self.action_dims = action_dims
        self.gripper_threshold = gripper_threshold

    def choose_from_chunks(
        self,
        previous_chunk: Optional[np.ndarray],
        current_chunk: Optional[np.ndarray],
        previous_horizon: int,
    ) -> AdaptiveDecision:
        """Choose a horizon from two consecutive predicted chunks."""

        if previous_chunk is None or current_chunk is None:
            return AdaptiveDecision(
                selected_horizon=self.mid_horizon,
                consistency_error=0.0,
                signal_source="missing_chunk",
                gripper_changed=False,
            )

        error = compute_chunk_consistency(
            previous_chunk,
            current_chunk,
            previous_horizon=previous_horizon,
            action_dims=self.action_dims,
        )
        gripper_changed = detect_gripper_change(current_chunk, self.gripper_threshold)
        return self._decision(error, gripper_changed, "chunk_consistency")

    def choose_from_executed_actions(self, actions: Sequence[Sequence[float]]) -> AdaptiveDecision:
        """Fallback when the server only returns one action at a time."""

        error = executed_action_variation(actions, action_dims=self.action_dims)
        gripper_changed = detect_gripper_change(np.asarray(actions), self.gripper_threshold)
        return self._decision(error, gripper_changed, "executed_action_variation_proxy")

    def _decision(
        self,
        consistency_error: float,
        gripper_changed: bool,
        signal_source: str,
    ) -> AdaptiveDecision:
        if gripper_changed or consistency_error > self.tau_high:
            horizon = self.min_horizon
        elif consistency_error > self.tau_low:
            horizon = self.mid_horizon
        else:
            horizon = self.max_horizon
        return AdaptiveDecision(
            selected_horizon=horizon,
            consistency_error=float(consistency_error),
            signal_source=signal_source,
            gripper_changed=bool(gripper_changed),
        )


def compute_chunk_consistency(
    previous_chunk: np.ndarray,
    current_chunk: np.ndarray,
    previous_horizon: int,
    action_dims: int = 6,
) -> float:
    """Mean L2 error on the overlapping future segment of two action chunks."""

    prev = np.asarray(previous_chunk, dtype=np.float32)
    curr = np.asarray(current_chunk, dtype=np.float32)
    if prev.ndim != 2 or curr.ndim != 2:
        raise ValueError("Chunks must have shape [horizon, action_dim]")

    chunk_len = min(prev.shape[0], curr.shape[0])
    overlap = chunk_len - int(previous_horizon)
    if overlap <= 0:
        return float("inf")

    dims = min(action_dims, prev.shape[1], curr.shape[1])
    prev_overlap = prev[int(previous_horizon): int(previous_horizon) + overlap, :dims]
    curr_overlap = curr[:overlap, :dims]
    diff = prev_overlap - curr_overlap
    return float(np.linalg.norm(diff, axis=1).mean())


def executed_action_variation(
    actions: Sequence[Sequence[float]],
    action_dims: int = 6,
) -> float:
    """Variation proxy for stacks that do not expose full predicted chunks."""

    arr = np.asarray(list(actions), dtype=np.float32)
    if arr.ndim != 2 or arr.shape[0] < 2:
        return 0.0
    dims = min(action_dims, arr.shape[1])
    diffs = np.diff(arr[:, :dims], axis=0)
    return float(np.linalg.norm(diffs, axis=1).mean())


def detect_gripper_change(
    actions_or_chunk: Optional[Iterable[Sequence[float]]],
    threshold: float = 0.25,
) -> bool:
    """Detect a meaningful gripper open/close change in the last action dim."""

    if actions_or_chunk is None:
        return False
    arr = np.asarray(list(actions_or_chunk), dtype=np.float32)
    if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 7:
        return False
    gripper = arr[:, -1]
    return bool(np.max(gripper) - np.min(gripper) > threshold)


def summarize_horizon_sequence(sequence: Sequence[int]) -> dict:
    if not sequence:
        return {
            "selected_horizon_mean": 0.0,
            "selected_horizon_min": 0,
            "selected_horizon_max": 0,
            "selected_horizon_sequence": "",
        }
    values = [int(x) for x in sequence]
    return {
        "selected_horizon_mean": float(np.mean(values)),
        "selected_horizon_min": int(np.min(values)),
        "selected_horizon_max": int(np.max(values)),
        "selected_horizon_sequence": ";".join(str(x) for x in values),
    }


def summarize_errors(errors: Sequence[float]) -> dict:
    if not errors:
        return {
            "consistency_error_mean": 0.0,
            "consistency_error_max": 0.0,
        }
    return {
        "consistency_error_mean": float(np.mean(errors)),
        "consistency_error_max": float(np.max(errors)),
    }
