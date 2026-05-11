"""Live feature extractor — produces the 5 sensor-only features the v4 model expects.

v4 contract (sensors-only, no step/procedure leakage):
    pupil_pcps_mean        — over the last 10 s of pupil samples
    pupil_diam_slope       — over the last 10 s of pupil samples
    blink_rate_30s         — count of non-tracking-loss blinks in last 30 s
    fixation_dur_mean_ms   — mean fixation duration in last 30 s (ms)
    fixation_dispersion_mean — mean fixation dispersion in last 30 s

Formulas mirror `ML Algorithm/scripts/lib/{pupil,blink,fixation}_features.py`
exactly so that training-time and serving-time values are comparable. Anything
that does not appear in `X_FEATURES.md` is intentionally left out.

`procedure_id` and `step_number` are NOT model features — including them lets
the model fall back on a deterministic step-number lookup instead of learning
from physiology. They're still passed in so we can stamp the prediction with
the operator's current step (for downstream UI routing), but they don't enter
the model input.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Order MUST match `FEATURE_COLS` in `ML Algorithm/scripts/07c_train_rf_pnorm.py`.
# Sensor features only — no step/procedure leakage.
FEATURE_NAMES: tuple[str, ...] = (
    "pupil_pcps_mean",
    "pupil_diam_slope",
    "blink_rate_30s",
    "fixation_dur_mean_ms",
    "fixation_dispersion_mean",
)


@dataclass(frozen=True)
class PupilBaseline:
    """Per-session pupil baseline used for PCPS."""

    eye0_mm: float
    eye1_mm: float
    mean_mm: float


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


def extract_features(
    *,
    pupil_t: np.ndarray,
    pupil_eye: np.ndarray,
    pupil_diam_mm: np.ndarray,
    blink_durations_s: np.ndarray,
    fix_durations_s: np.ndarray,
    fix_dispersion: np.ndarray,
    baseline: PupilBaseline | None,
    procedure_id: int,
    step_number: int,
    cumulative_session_time_s: float,
    window_len_s: float,
    expected_pupil_rate_hz_per_eye: float,
    min_data_yield: float,
) -> tuple[dict[str, float | int | None], bool, dict[str, float]]:
    """Compute the 5 v4 sensor features over the supplied window slices.

    Args:
        pupil_t / pupil_eye / pupil_diam_mm: aligned arrays of confidence-
            filtered pupil samples whose timestamps fall inside the current
            10-second pupil window.
        blink_durations_s: durations of non-tracking-loss blinks whose start
            timestamps fall inside the current 30-second blink window.
        fix_durations_s / fix_dispersion: aligned arrays of fixations whose
            start timestamps fall inside the current 30-second fixation window.
        baseline: per-session pupil baseline (or None if not yet ready).
        procedure_id / step_number / cumulative_session_time_s: live task
            context — passed through for prediction stamping but NOT used as
            model inputs in v4.

    Returns:
        (features, is_valid, qa) where:
          features  - dict keyed by FEATURE_NAMES (NaN where the source had
                      no data — Random Forest predictor handles via the
                      pipeline's SimpleImputer);
          is_valid  - True iff `pupil_data_yield >= min_data_yield` OR at
                      least one fixation fell in the window;
          qa        - dict of internal QA values (data yield, sample counts).
    """
    n_pupil = int(len(pupil_t))
    expected = max(1.0, expected_pupil_rate_hz_per_eye * 2.0 * window_len_s)
    pupil_data_yield = float(n_pupil) / expected

    # ---- pupil_pcps_mean ------------------------------------------------- #
    pcps_mean = float("nan")
    if (
        n_pupil > 0
        and baseline is not None
        and not np.isnan(baseline.mean_mm)
        and baseline.mean_mm > 0
    ):
        e0_mask = pupil_eye == 0
        e1_mask = pupil_eye == 1
        pieces: list[np.ndarray] = []
        if e0_mask.any() and not np.isnan(baseline.eye0_mm) and baseline.eye0_mm > 0:
            pieces.append((pupil_diam_mm[e0_mask] - baseline.eye0_mm) / baseline.eye0_mm)
        if e1_mask.any() and not np.isnan(baseline.eye1_mm) and baseline.eye1_mm > 0:
            pieces.append((pupil_diam_mm[e1_mask] - baseline.eye1_mm) / baseline.eye1_mm)
        if pieces:
            pcps_mean = float(np.mean(np.concatenate(pieces)))

    # ---- pupil_diam_slope ----------------------------------------------- #
    pupil_slope = _safe_slope(pupil_t, pupil_diam_mm) if n_pupil >= 3 else float("nan")

    # ---- blink_rate_30s --------------------------------------------------- #
    # Direct count over the 30-second blink window (no /min extrapolation).
    blink_rate_30s = float(len(blink_durations_s))

    # ---- fixation_dur_mean_ms ------------------------------------------- #
    n_fix = int(len(fix_durations_s))
    fix_dur_mean_ms = float(np.mean(fix_durations_s) * 1000.0) if n_fix else float("nan")

    # ---- fixation_dispersion_mean --------------------------------------- #
    if n_fix:
        disp_clean = fix_dispersion[~np.isnan(fix_dispersion)]
        fix_disp_mean = float(np.mean(disp_clean)) if len(disp_clean) else float("nan")
    else:
        fix_disp_mean = float("nan")

    features: dict[str, float | int | None] = {
        "pupil_pcps_mean": pcps_mean,
        "pupil_diam_slope": pupil_slope,
        "blink_rate_30s": blink_rate_30s,
        "fixation_dur_mean_ms": fix_dur_mean_ms,
        "fixation_dispersion_mean": fix_disp_mean,
    }

    is_valid = (pupil_data_yield >= min_data_yield) or (n_fix >= 1)

    qa = {
        "pupil_n_samples": float(n_pupil),
        "pupil_data_yield": pupil_data_yield,
        "blink_count": float(len(blink_durations_s)),
        "fixation_count": float(n_fix),
        # Stamped passthrough — not used by the model, but kept for the UI.
        "procedure_id": int(procedure_id),
        "step_number": int(step_number),
        "cumulative_session_time_s": float(cumulative_session_time_s),
    }
    return features, is_valid, qa
