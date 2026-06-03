"""Live feature extractor — produces the 4 sensor-only features the model expects.

Contract (sensors-only, no step/procedure leakage):
    pupil_pcps_mean        — over the last 10 s of pupil samples
    pupil_diam_slope       — over the last 10 s of pupil samples
    blink_rate_30s         — count of non-tracking-loss blinks in last 30 s
    fixation_dur_mean_ms   — mean fixation duration in last 30 s (ms)

(fixation_dispersion_mean was dropped — it added little accuracy and was
correlated with fixation_dur_mean_ms.)

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

# Order MUST match `FEATURE_COLS` in `ML Algorithm/scripts/07d_train_rf_tuned.py`.
# Sensor features only — no step/procedure leakage.
FEATURE_NAMES: tuple[str, ...] = (
    "pupil_pcps_mean",
    "pupil_diam_slope",
    "blink_rate_30s",
    "fixation_dur_mean_ms",
)

# Training-distribution envelope per feature, computed from the 18,348
# valid windows in `ML Algorithm/data/_processed/*/X_window.parquet`.
# `lo` and `hi` are the 1st and 99th percentiles of the training data —
# the model has effectively never seen values outside this range, so any
# prediction made on a value beyond these bounds is an out-of-distribution
# extrapolation. The strategy (see `settings.feature_sanitize_strategy`)
# decides what to do with values outside [lo, hi]:
#
#   "clip" (DEFAULT) — clamp to [lo, hi]. Hands the model an in-envelope
#             value that it has learned a class boundary for. Preserves
#             the *direction* of the signal: a live blink rate of 49
#             becomes 21, still high relative to the training median of
#             3 but no longer extrapolating into untrained territory.
#   "mask"  — replace with NaN. The training pipeline's SimpleImputer
#             fills with the training MEDIAN (class-neutral), so the model
#             effectively ignores that feature for this window. Useful
#             when a sensor channel is producing nonsense.
#   "off"   — pass the live value straight through.
#
# Regenerate bounds by running `07d_train_rf_tuned.py` and inspecting
# `X[col].describe(percentiles=[0.01, 0.99])`.
FEATURE_TRAINING_BOUNDS: dict[str, tuple[float, float]] = {
    "pupil_pcps_mean":          (-0.29, 1.04),
    "pupil_diam_slope":         (-0.13, 0.13),
    "blink_rate_30s":           (0.0,   21.0),
    "fixation_dur_mean_ms":     (100.0, 211.0),
}


def sanitize_features_to_training_distribution(
    features: dict[str, float | int | None],
    *,
    strategy: str = "clip",
) -> tuple[dict[str, float | int | None], dict[str, str], dict[str, float]]:
    """Bring live features into agreement with the training distribution.

    Args:
        features: raw live feature dict (the output of `extract_features`).
        strategy: "mask" (out-of-distribution → NaN), "clip" (clamp to
            training envelope), or "off" (pass through unchanged).

    Returns:
        (sanitized_features, actions, deltas) where:
          * `sanitized_features` is the dict to hand to the model;
          * `actions[name]` is "masked", "clipped", or absent (in-distribution);
          * `deltas[name]` is the numeric change for clipped features (always
            present alongside actions["clipped"]); for masked features it's
            the value that was masked, useful for diagnostic logging.
    """
    if strategy == "off":
        return dict(features), {}, {}

    out: dict[str, float | int | None] = dict(features)
    actions: dict[str, str] = {}
    deltas: dict[str, float] = {}
    for name, (lo, hi) in FEATURE_TRAINING_BOUNDS.items():
        v = out.get(name)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv != fv:  # NaN — already missing, nothing to do
            continue
        if lo <= fv <= hi:
            continue  # in-distribution, untouched

        if strategy == "mask":
            actions[name] = "masked"
            deltas[name] = fv  # carry the original value for logging
            out[name] = float("nan")
        elif strategy == "clip":
            clipped = min(hi, max(lo, fv))
            actions[name] = "clipped"
            deltas[name] = clipped - fv
            out[name] = clipped
        else:
            raise ValueError(
                f"Unknown sanitize strategy {strategy!r}; use 'mask', 'clip', or 'off'."
            )
    return out, actions, deltas


# Back-compat alias — older callers used `clip_features_to_training_distribution`.
# Keep them working but forward to the new function in clip mode.
def clip_features_to_training_distribution(
    features: dict[str, float | int | None],
) -> tuple[dict[str, float | int | None], dict[str, float]]:
    sanitized, _actions, deltas = sanitize_features_to_training_distribution(
        features, strategy="clip"
    )
    return sanitized, deltas


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
    baseline: PupilBaseline | None,
    procedure_id: int,
    step_number: int,
    cumulative_session_time_s: float,
    window_len_s: float,
    expected_pupil_rate_hz_per_eye: float,
    min_data_yield: float,
) -> tuple[dict[str, float | int | None], bool, dict[str, float]]:
    """Compute the 4 sensor features over the supplied window slices.

    Args:
        pupil_t / pupil_eye / pupil_diam_mm: aligned arrays of confidence-
            filtered pupil samples whose timestamps fall inside the current
            10-second pupil window.
        blink_durations_s: durations of non-tracking-loss blinks whose start
            timestamps fall inside the current 30-second blink window.
        fix_durations_s: durations of fixations whose start timestamps fall
            inside the current 30-second fixation window.
        baseline: per-session pupil baseline (or None if not yet ready).
        procedure_id / step_number / cumulative_session_time_s: live task
            context — passed through for prediction stamping but NOT used as
            model inputs.

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

    features: dict[str, float | int | None] = {
        "pupil_pcps_mean": pcps_mean,
        "pupil_diam_slope": pupil_slope,
        "blink_rate_30s": blink_rate_30s,
        "fixation_dur_mean_ms": fix_dur_mean_ms,
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
