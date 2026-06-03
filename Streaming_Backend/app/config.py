"""Runtime configuration.

These knobs MUST stay aligned with `ML Algorithm/scripts/lib/config.py` so that
the live feature extractor produces values comparable to the training-time
features. The model is trained on a 10 s window with 1 s stride, a 60 s
baseline, and confidence >= 0.6 — the live system has to use the same.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _env_path(name: str, default: str) -> Path:
    raw = os.getenv(name)
    return Path(raw if raw not in (None, "") else default).expanduser()


def _csv_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


class Settings:
    app_name: str = os.getenv("APP_NAME", "rtaps-streaming-backend")
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = _env_int("PORT", 8000)

    # ---- Feature/window contract (must match training pipeline) ----------
    # Per-feature windows — match ML Algorithm/scripts/lib/config.py
    # (WINDOW_LEN_S_PUPIL / FIXATION / BLINK).
    window_len_s: float = _env_float("WINDOW_LEN_S", 10.0)              # pupil
    fixation_window_len_s: float = _env_float("FIXATION_WINDOW_LEN_S", 30.0)
    blink_window_len_s: float = _env_float("BLINK_WINDOW_LEN_S", 30.0)
    stride_s: float = _env_float("STRIDE_S", 1.0)
    baseline_duration_s: float = _env_float("BASELINE_DURATION_S", 120.0)
    min_confidence: float = _env_float("MIN_CONFIDENCE", 0.6)
    blink_tracking_loss_s: float = _env_float("BLINK_TRACKING_LOSS_S", 2.0)
    expected_pupil_rate_hz_per_eye: float = _env_float("EXPECTED_PUPIL_RATE_HZ", 60.0)
    min_data_yield: float = _env_float("MIN_DATA_YIELD", 0.6)

    # ---- Workload smoother -----------------------------------------------
    # Consecutive seconds the new candidate label must hold before the
    # displayed instruction level changes. Lower values = more responsive UI
    # (instructions change ~3 s after the model first sees the new level),
    # higher values = more stable but laggier. Direction-guarded one step at
    # a time (low ↔ medium ↔ high).
    workload_smoother_stability_s: int = _env_int("WORKLOAD_SMOOTHER_STABILITY_S", 3)

    # ---- Feature sanitization (train/serve skew guard) ------------------
    # Training data (`X_window.parquet`) has tight per-feature distributions
    # (computed from offline Pupil-player exports). Two live features
    # consistently drift outside those bounds:
    #
    #     feature                     training 99th   live typical
    #     ---------------------------------------------------------
    #     fixation_dur_mean_ms        211             ~300
    #     blink_rate_30s              21              ~30–50   (more
    #         blinks than the research-subject training population)
    #
    # The model's permutation importance is fairly balanced across the
    # four sensor features, so no single feature dominates and the old
    # "lock to HIGH on OOD fixations" failure mode is mild.
    #
    # Strategy options:
    #   "clip" (DEFAULT) — clamp out-of-distribution values to the
    #       [1st-%ile, 99th-%ile] training envelope. Preserves the
    #       *direction* of each feature (high blink stays high, just
    #       capped at 21 instead of 49), which is what we want when
    #       the model has no single dominant feature.
    #   "mask" — replace OOD values with NaN. SimpleImputer fills with
    #       the training median (class-neutral) — useful only if a
    #       feature is producing nonsense (e.g. a stuck detector),
    #       not as a default.
    #   "off"  — pass live values straight through.
    feature_sanitize_strategy: str = os.getenv("FEATURE_SANITIZE_STRATEGY", "clip")
    # Diagnostic: log raw feature values (and sanitization deltas if any)
    # every N prediction ticks. 0 disables. Default 10 → roughly every
    # 10 s of operating time so the operator can sanity-check at a glance.
    feature_log_every_n_ticks: int = _env_int("FEATURE_LOG_EVERY_N_TICKS", 10)

    # ---- Model -----------------------------------------------------------
    model_path: Path = _env_path(
        "MODEL_PATH",
        str(Path(__file__).resolve().parents[2] / "ML Algorithm" / "models" / "v5_rf_tuned.joblib"),
    )

    # ---- Optional remote inference (forward features, get back prediction)
    fargate_inference_url: str = os.getenv("FARGATE_INFERENCE_URL", "")
    api_token: str = os.getenv("API_TOKEN", "")
    model_timeout_sec: float = _env_float("MODEL_TIMEOUT_SEC", 5.0)

    # ---- Optional outbound webhook (push predictions to RTAPS frontend) --
    prediction_webhook_url: str = os.getenv("PREDICTION_WEBHOOK_URL", "")

    # ---- House-keeping ---------------------------------------------------
    # When a stream goes idle (no pupil samples) for this many seconds, drop it.
    session_idle_ttl_s: float = _env_float("SESSION_IDLE_TTL_S", 600.0)

    # ---- CORS (RTAPS React dev server on :3000 by default) ---------------
    cors_origins: list[str] = _csv_list(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )


settings = Settings()
