"""Clock conversions between Pupil's `synced_s` and UNIX wall-clock time."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClockAnchor:
    """Anchor mapping Pupil synced_s ↔ UNIX seconds for one recording."""

    unix_at_pupil_start: float
    synced_at_pupil_start: float
    pupil_duration_s: float

    def synced_to_unix(self, synced_t: float) -> float:
        return (synced_t - self.synced_at_pupil_start) + self.unix_at_pupil_start

    def unix_to_synced(self, unix_t: float) -> float:
        return (unix_t - self.unix_at_pupil_start) + self.synced_at_pupil_start

    @property
    def unix_end(self) -> float:
        return self.unix_at_pupil_start + self.pupil_duration_s

    @property
    def synced_end(self) -> float:
        return self.synced_at_pupil_start + self.pupil_duration_s


def overlap_seconds(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def overlap_fraction(
    a_start: float, a_end: float, b_start: float, b_end: float
) -> float:
    """Overlap divided by the *shorter* of the two intervals."""
    a_len = max(0.0, a_end - a_start)
    b_len = max(0.0, b_end - b_start)
    denom = min(a_len, b_len) if min(a_len, b_len) > 0 else max(a_len, b_len)
    if denom <= 0:
        return 0.0
    return overlap_seconds(a_start, a_end, b_start, b_end) / denom
