"""Workload instruction smoother — prevents jarring per-second level changes.

Raw model predictions arrive every second. Showing those directly would flip
the on-screen instruction every few seconds, which is disruptive and
unreadable for the operator.

This module applies one constraint before a level change is shown:

**Stability gate** — a new candidate level must be the continuous prediction
for at least `stability_window_s` consecutive seconds before it commits and
becomes the displayed level. This filters out single-second noise from
momentary blinks, fixation gaps, or transient feature drift.

The smoother is *symmetric*: both upgrades (low → high) and downgrades
(high → low) require the same `stability_window_s` of supporting evidence.
That's the property the operator UI relies on — once the model has
genuinely changed its mind for 3 s, the instruction block flips.

Initial level is **low** by default (operators start each step with the
"no extra guidance" view); InferenceLoop also calls `force_level("low")`
on every step transition so the new step starts fresh.

Usage per active session (InferenceLoop keeps one smoother per stream_id):

    smoother = WorkloadSmoother(stability_window_s=3, initial_level="low")

    # on each 1-second tick:
    stable_label = smoother.update(raw_model_label)

    # on step boundary (preferred — starts the new step at LOW):
    smoother.force_level("low")

    # on session end:
    smoother.reset()
"""
from __future__ import annotations

from typing import Optional


# Transition graph. Kept permissive so the smoother works with both the
# legacy 3-class output (low / medium / high) and the current 2-class
# output (low / high). The stability gate is the only debouncer.
_ALLOWED: dict[str, set[str]] = {
    "low":    {"medium", "high"},
    "medium": {"low", "high"},
    "high":   {"medium", "low"},
}

VALID_LABELS = frozenset({"low", "medium", "high"})


class WorkloadSmoother:
    """Per-session workload level debouncer."""

    def __init__(
        self,
        stability_window_s: int = 3,
        initial_level: str = "low",
    ) -> None:
        if stability_window_s < 1:
            raise ValueError("stability_window_s must be >= 1")
        if initial_level not in VALID_LABELS:
            raise ValueError(
                f"initial_level must be one of {sorted(VALID_LABELS)}; got {initial_level!r}"
            )
        self._window = stability_window_s
        # Each step begins at the configured initial level (default "low")
        # so the UI always shows the "no extra guidance" view first; the
        # stability gate then governs every upgrade or downgrade from there.
        self._current: str = initial_level
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
            return self._current

        # Already at this level → reinforce, clear any pending candidate
        if raw_label == self._current:
            self._candidate = None
            self._candidate_count = 0
            return self._current

        # Direction guard (no-op with the current permissive transition map)
        if raw_label not in _ALLOWED[self._current]:
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

    def force_level(self, level: str) -> None:
        """Hard-set the displayed level and clear any pending candidate.

        Called by InferenceLoop on every step transition with `"low"` so
        each step opens with the "no extra guidance" view. From there the
        stability gate governs every upgrade / downgrade.
        """
        if level not in VALID_LABELS:
            raise ValueError(
                f"level must be one of {sorted(VALID_LABELS)}; got {level!r}"
            )
        self._current = level
        self._candidate = None
        self._candidate_count = 0

    def reset_candidate(self) -> None:
        """Clear any pending transition without changing the displayed level.

        Retained for callers that want to flush noise without forcing the
        level. Prefer `force_level("low")` at step boundaries.
        """
        self._candidate = None
        self._candidate_count = 0

    def reset(self) -> None:
        """Full reset — call at session end. Returns the smoother to its
        configured initial level (defaults to "low")."""
        self._current = "low"
        self._candidate = None
        self._candidate_count = 0

    # ------------------------------------------------------------------ #

    @property
    def current_level(self) -> str:
        """The level currently shown to the operator (starts at the configured
        initial level — default "low" — and updates only when a candidate
        clears the stability gate)."""
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
