"""Workload instruction smoother — prevents jarring per-second level changes.

Raw model predictions arrive every second. Showing those directly would flip
the on-screen instruction (Low / Medium / High) every few seconds, which is
disruptive and unreadable for the operator.

This module applies two constraints before a level change is shown:

1. **Stability gate** — the new level must be the continuous prediction for
   at least `stability_window_s` consecutive seconds before committing.

2. **Direction guard** — the level can only move one step at a time:
       low ↔ medium ↔ high
   A jump from "high" directly to "low" (or vice-versa) is blocked; the
   transition must pass through "medium" first. This mirrors real cognitive
   load dynamics and filters out prediction noise from momentary blinks or
   fixation gaps.

Usage per active session (InferenceLoop keeps one smoother per stream_id):

    smoother = WorkloadSmoother(stability_window_s=30)

    # on each 1-second tick:
    stable_label = smoother.update(raw_model_label)

    # on session start or step change (optional — clears candidate only):
    smoother.reset_candidate()

    # on session end:
    smoother.reset()
"""
from __future__ import annotations

from typing import Optional


_ALLOWED: dict[str, set[str]] = {
    "low":    {"medium"},
    "medium": {"low", "high"},
    "high":   {"medium"},
}

VALID_LABELS = frozenset({"low", "medium", "high"})


class WorkloadSmoother:
    """Per-session workload level debouncer."""

    def __init__(self, stability_window_s: int = 30) -> None:
        if stability_window_s < 1:
            raise ValueError("stability_window_s must be >= 1")
        self._window = stability_window_s
        self._current: Optional[str] = None   # level currently shown to operator
        self._candidate: Optional[str] = None  # level trying to become current
        self._candidate_count: int = 0         # consecutive seconds at candidate

    # ------------------------------------------------------------------ #

    def update(self, raw_label: str) -> str:
        """Feed one raw per-second prediction; return the stable display level.

        Args:
            raw_label: one of "low", "medium", "high"

        Returns:
            The level that should be shown to the operator right now.
        """
        if raw_label not in VALID_LABELS:
            # Unknown label — keep current, don't crash
            return self._current or raw_label

        # Bootstrap: first prediction seeds the level immediately
        if self._current is None:
            self._current = raw_label
            return self._current

        # Already at this level → reinforce, clear any pending candidate
        if raw_label == self._current:
            self._candidate = None
            self._candidate_count = 0
            return self._current

        # Direction guard: only allow adjacent transitions
        if raw_label not in _ALLOWED[self._current]:
            # Blocked (e.g. high → low); reset candidate
            self._candidate = None
            self._candidate_count = 0
            return self._current

        # Accumulate evidence for the candidate
        if raw_label == self._candidate:
            self._candidate_count += 1
        else:
            self._candidate = raw_label
            self._candidate_count = 1

        # Commit when stable for the full window
        if self._candidate_count >= self._window:
            self._current = self._candidate
            self._candidate = None
            self._candidate_count = 0

        return self._current

    # ------------------------------------------------------------------ #

    def reset_candidate(self) -> None:
        """Clear any pending transition without changing the displayed level.

        Call this at step boundaries: the shown level carries over, but the
        30-second clock restarts so the new step's predictions accumulate
        fresh before any instruction change is triggered.
        """
        self._candidate = None
        self._candidate_count = 0

    def reset(self) -> None:
        """Full reset — call at session end / session start."""
        self._current = None
        self._candidate = None
        self._candidate_count = 0

    # ------------------------------------------------------------------ #

    @property
    def current_level(self) -> Optional[str]:
        """The level currently shown to the operator (None before first tick)."""
        return self._current

    @property
    def candidate_level(self) -> Optional[str]:
        """The candidate level accumulating, or None if stable."""
        return self._candidate

    @property
    def candidate_seconds(self) -> int:
        """Consecutive seconds the candidate has been seen."""
        return self._candidate_count

    @property
    def seconds_until_change(self) -> Optional[int]:
        """Remaining seconds until the candidate commits, or None if stable."""
        if self._candidate is None:
            return None
        return max(0, self._window - self._candidate_count)

    def state_dict(self) -> dict:
        """Serialisable snapshot for the dashboard endpoint."""
        return {
            "current_level": self._current,
            "candidate_level": self._candidate,
            "candidate_seconds": self._candidate_count,
            "stability_window_s": self._window,
            "seconds_until_change": self.seconds_until_change,
        }
