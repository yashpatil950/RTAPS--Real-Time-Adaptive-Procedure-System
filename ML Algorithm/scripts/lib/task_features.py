"""Per-window task / procedure-context features.

These are causal: at decision time `t` we use only what would be visible to
the live system. Two exceptions are documented in feature_dictionary.md:
`step_sub_steps_shown_eventually` and `step_exceeded_threshold_eventually`
are end-of-step booleans; we expose them as features because they are very
predictive but flag them clearly so they can be excluded if you want a strictly
causal feature set.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TASK_FEATURE_NAMES = [
    "step_number",
    "step_id",
    "n_steps_remaining",
    "step_threshold_s",
    "time_in_step_so_far_s",
    "is_over_threshold_now",
    "progress_vs_threshold",
    "step_sub_steps_shown_eventually",
    "step_exceeded_threshold_eventually",
    "cumulative_session_time_s",
    "cumulative_blink_count_session",
    "cumulative_long_blink_count_session",
    "frac_window_in_current_step",
]

PROGRESS_CAP = 5.0


def extract_task(
    *,
    decision_t: float,
    window_start: float,
    window_len_s: float,
    step_row: pd.Series,
    n_steps_total: int,
    session_start_synced: float,
    cum_blink_count: int,
    cum_long_blink_count: int,
) -> dict[str, float]:
    out: dict[str, float] = {k: float("nan") for k in TASK_FEATURE_NAMES}
    step_start = float(step_row["start_synced_t"])
    step_end = float(step_row["end_synced_t"])
    step_threshold = float(step_row.get("threshold_s", float("nan")))

    out["step_number"] = float(int(step_row["step_number"]))
    out["step_id"] = float(int(step_row["step_id"]))
    out["n_steps_remaining"] = float(n_steps_total - int(step_row["step_number"]))

    out["step_threshold_s"] = step_threshold
    time_in_step = max(0.0, decision_t - step_start)
    out["time_in_step_so_far_s"] = time_in_step
    if not np.isnan(step_threshold) and step_threshold > 0:
        out["is_over_threshold_now"] = float(time_in_step > step_threshold)
        out["progress_vs_threshold"] = float(min(time_in_step / step_threshold, PROGRESS_CAP))
    else:
        out["is_over_threshold_now"] = float("nan")
        out["progress_vs_threshold"] = float("nan")

    out["step_sub_steps_shown_eventually"] = float(bool(step_row.get("sub_steps_shown", False)))
    out["step_exceeded_threshold_eventually"] = float(bool(step_row.get("exceeded_threshold", False)))

    out["cumulative_session_time_s"] = max(0.0, decision_t - session_start_synced)
    out["cumulative_blink_count_session"] = float(int(cum_blink_count))
    out["cumulative_long_blink_count_session"] = float(int(cum_long_blink_count))

    overlap = max(0.0, min(decision_t, step_end) - max(window_start, step_start))
    out["frac_window_in_current_step"] = float(min(overlap / window_len_s, 1.0))
    return out
