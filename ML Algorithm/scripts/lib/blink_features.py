"""Per-window blink features computed from blinks_clean.parquet.

NOTE: as of v4, the canonical blink rate feature is `blink_rate_30s` —
count of (non-tracking-loss) blinks in a 30-second sliding window. The
old `blink_rate_per_min` (60-second window, extrapolated to /min) has
been replaced because:
  - 30 s gives faster reaction to workload changes
  - the value is a direct count (no extrapolation), so easier to interpret
"""
from __future__ import annotations

import numpy as np
import pandas as pd

BLINK_FEATURE_NAMES = [
    "blink_count",
    "blink_rate_30s",                # was blink_rate_per_min
    "blink_dur_mean_s",
    "blink_dur_std_s",
    "blink_inter_interval_mean_s",
    "blink_inter_interval_cv",
    "blink_long_count",
]


def extract(
    blinks_window: pd.DataFrame,
    *,
    window_len_s: float,
    long_thresh_s: float,
) -> dict[str, float]:
    """Compute blink features. Blinks flagged tracking_loss are excluded.

    `blink_rate_30s` = count of non-tracking-loss blinks in the supplied
    `window_len_s` window (which is 30 s for v4 per `lib/config.py`).
    """
    out: dict[str, float] = {k: float("nan") for k in BLINK_FEATURE_NAMES}
    out["blink_count"] = 0.0
    out["blink_rate_30s"] = 0.0
    out["blink_long_count"] = 0.0
    if blinks_window is None or len(blinks_window) == 0:
        return out

    bl = blinks_window
    if "tracking_loss" in bl.columns:
        bl = bl[~bl["tracking_loss"].astype(bool)]
    if bl.empty:
        return out

    n = len(bl)
    out["blink_count"] = float(n)
    # Direct count over the window (no /min extrapolation).
    out["blink_rate_30s"] = float(n)
    durs = bl["duration_s"].to_numpy(dtype=float)
    out["blink_dur_mean_s"] = float(np.mean(durs))
    if n >= 2:
        out["blink_dur_std_s"] = float(np.std(durs, ddof=0))
    out["blink_long_count"] = float(int((durs >= long_thresh_s).sum()))

    if n >= 2:
        starts = np.sort(bl["start_synced_t"].to_numpy(dtype=float))
        ibis = np.diff(starts)
        if len(ibis) > 0:
            mean_ibi = float(np.mean(ibis))
            out["blink_inter_interval_mean_s"] = mean_ibi
            std_ibi = float(np.std(ibis, ddof=0))
            out["blink_inter_interval_cv"] = (std_ibi / mean_ibi) if mean_ibi > 0 else float("nan")
    return out
