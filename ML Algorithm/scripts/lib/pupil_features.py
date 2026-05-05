"""Per-window pupil-diameter features computed from pupil_clean.parquet."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PUPIL_FEATURE_NAMES = [
    "pupil_n_samples",
    "pupil_data_yield",
    "pupil_diam_mean",
    "pupil_diam_std",
    "pupil_diam_median",
    "pupil_diam_iqr",
    "pupil_diam_slope",
    "pupil_diam_range",
    "pupil_eye_asymmetry",
    "pupil_pcps_mean",
    "pupil_pcps_std",
    # z-scored variants vs participant baseline
    "pupil_diam_mean_z",
    "pupil_diam_slope_z",
]


@dataclass
class PupilBaseline:
    """Per-session pupil baseline used for PCPS and z-scoring."""

    eye0_mm: float
    eye1_mm: float
    mean_mm: float

    @classmethod
    def from_row(cls, row) -> "PupilBaseline":
        return cls(
            eye0_mm=float(row.get("pupil_baseline_mm_eye0", float("nan")) or float("nan")),
            eye1_mm=float(row.get("pupil_baseline_mm_eye1", float("nan")) or float("nan")),
            mean_mm=float(row.get("pupil_baseline_mm_mean", float("nan")) or float("nan")),
        )


def _safe_slope(t: np.ndarray, y: np.ndarray) -> float:
    if len(t) < 3:
        return float("nan")
    t = t.astype(float)
    y = y.astype(float)
    t_c = t - t.mean()
    denom = float(np.dot(t_c, t_c))
    if denom <= 0:
        return float("nan")
    return float(np.dot(t_c, y - y.mean()) / denom)


def extract(
    pupil_window: pd.DataFrame,
    *,
    window_len_s: float,
    expected_rate_hz_per_eye: float,
    baseline: PupilBaseline | None,
) -> dict[str, float]:
    """Compute pupil features over a pre-sliced [t-W, t] window."""
    out: dict[str, float] = {k: float("nan") for k in PUPIL_FEATURE_NAMES}
    n = len(pupil_window)
    out["pupil_n_samples"] = float(n)
    expected = max(1.0, expected_rate_hz_per_eye * 2.0 * window_len_s)
    out["pupil_data_yield"] = float(n / expected)
    if n == 0:
        return out

    diam = pupil_window["diameter_mm"].to_numpy(dtype=float)
    t_all = pupil_window["synced_t"].to_numpy(dtype=float)
    eye = pupil_window["eye_id"].to_numpy(dtype=int)

    out["pupil_diam_mean"] = float(np.mean(diam))
    out["pupil_diam_std"] = float(np.std(diam, ddof=0))
    out["pupil_diam_median"] = float(np.median(diam))
    q1, q3 = np.percentile(diam, [25, 75])
    out["pupil_diam_iqr"] = float(q3 - q1)
    out["pupil_diam_range"] = float(diam.max() - diam.min())
    out["pupil_diam_slope"] = _safe_slope(t_all, diam)

    e0 = diam[eye == 0]
    e1 = diam[eye == 1]
    if len(e0) and len(e1):
        out["pupil_eye_asymmetry"] = abs(float(np.mean(e0)) - float(np.mean(e1)))

    if baseline is not None and not np.isnan(baseline.mean_mm) and baseline.mean_mm > 0:
        pcps_e0 = (e0 - baseline.eye0_mm) / baseline.eye0_mm if not np.isnan(baseline.eye0_mm) else np.array([])
        pcps_e1 = (e1 - baseline.eye1_mm) / baseline.eye1_mm if not np.isnan(baseline.eye1_mm) else np.array([])
        per_eye = np.concatenate([pcps_e0, pcps_e1])
        if len(per_eye):
            out["pupil_pcps_mean"] = float(np.mean(per_eye))
            out["pupil_pcps_std"] = float(np.std(per_eye, ddof=0))
        # z-score variants: same formula but divide by baseline std proxy.
        # We don't have a proper baseline std stored, so use baseline.mean_mm as a
        # scale (gives a unitless quantity comparable across participants).
        out["pupil_diam_mean_z"] = (out["pupil_diam_mean"] - baseline.mean_mm) / baseline.mean_mm
        if not np.isnan(out["pupil_diam_slope"]):
            out["pupil_diam_slope_z"] = out["pupil_diam_slope"] / baseline.mean_mm

    return out
