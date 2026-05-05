"""Per-window fixation features computed from fixations_clean.parquet."""
from __future__ import annotations

import numpy as np
import pandas as pd

FIXATION_FEATURE_NAMES = [
    "fixation_count",
    "fixation_rate_per_sec",
    "fixation_dur_mean_ms",
    "fixation_dur_std_ms",
    "fixation_dur_median_ms",
    "fixation_dispersion_mean",
    "fixation_dispersion_std",
    "fixation_time_in_fixation_ratio",
    "fixation_saccade_amp_mean",
]


def extract(
    fix_window: pd.DataFrame,
    *,
    window_len_s: float,
) -> dict[str, float]:
    out: dict[str, float] = {k: float("nan") for k in FIXATION_FEATURE_NAMES}
    out["fixation_count"] = 0.0
    out["fixation_rate_per_sec"] = 0.0
    out["fixation_time_in_fixation_ratio"] = 0.0
    if fix_window is None or len(fix_window) == 0:
        return out

    n = len(fix_window)
    out["fixation_count"] = float(n)
    out["fixation_rate_per_sec"] = float(n) / window_len_s

    durs_s = fix_window["duration_s"].to_numpy(dtype=float)
    durs_ms = durs_s * 1000.0
    out["fixation_dur_mean_ms"] = float(np.mean(durs_ms))
    out["fixation_dur_median_ms"] = float(np.median(durs_ms))
    if n >= 2:
        out["fixation_dur_std_ms"] = float(np.std(durs_ms, ddof=0))
    out["fixation_time_in_fixation_ratio"] = float(np.sum(durs_s)) / window_len_s

    if "dispersion" in fix_window.columns:
        disp = fix_window["dispersion"].to_numpy(dtype=float)
        disp = disp[~np.isnan(disp)]
        if len(disp):
            out["fixation_dispersion_mean"] = float(np.mean(disp))
            if len(disp) >= 2:
                out["fixation_dispersion_std"] = float(np.std(disp, ddof=0))

    if n >= 2 and {"norm_pos_x", "norm_pos_y"}.issubset(fix_window.columns):
        x = fix_window["norm_pos_x"].to_numpy(dtype=float)
        y = fix_window["norm_pos_y"].to_numpy(dtype=float)
        d = np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2)
        d = d[~np.isnan(d)]
        if len(d):
            out["fixation_saccade_amp_mean"] = float(np.mean(d))
    return out
