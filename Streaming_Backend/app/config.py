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
    window_len_s: float = _env_float("WINDOW_LEN_S", 10.0)
    stride_s: float = _env_float("STRIDE_S", 1.0)
    baseline_duration_s: float = _env_float("BASELINE_DURATION_S", 120.0)
    min_confidence: float = _env_float("MIN_CONFIDENCE", 0.6)
    blink_tracking_loss_s: float = _env_float("BLINK_TRACKING_LOSS_S", 2.0)
    expected_pupil_rate_hz_per_eye: float = _env_float("EXPECTED_PUPIL_RATE_HZ", 60.0)
    min_data_yield: float = _env_float("MIN_DATA_YIELD", 0.6)

    # ---- Model -----------------------------------------------------------
    model_path: Path = _env_path(
        "MODEL_PATH",
        str(Path(__file__).resolve().parents[2] / "ML Algorithm" / "models" / "v4_rf_pnorm.joblib"),
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
