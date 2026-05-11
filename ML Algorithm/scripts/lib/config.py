"""Pipeline configuration. Single source of truth for paths and tunables."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ML_ROOT = REPO_ROOT / "ML Algorithm"
RAW_DATA_ROOT = ML_ROOT / "data"
PROCESSED_ROOT = RAW_DATA_ROOT / "_processed"

RTAPS_SESSIONS_CSV = REPO_ROOT / "RTAPS" / "data" / "rtaps_sessions.csv"
PROCEDURES_JS = REPO_ROOT / "RTAPS" / "src" / "data" / "procedures.js"

LAPTOPS = ("Lenovo_laptop", "Dr_Zahabi_laptop", "Loaner_laptop")

LAPTOP_SHORT = {
    "Lenovo_laptop": "lenovo",
    "Dr_Zahabi_laptop": "zahabi",
    "Loaner_laptop": "loaner",
}

PROCEDURE_ID_TO_SLUG = {
    1: "centrifuge",
    2: "column_flushing",
    3: "pressure_testing",
}
PROCEDURE_SLUG_TO_ID = {v: k for k, v in PROCEDURE_ID_TO_SLUG.items()}
PROCEDURE_SLUGS = tuple(PROCEDURE_ID_TO_SLUG.values())

WINDOW_LEN_S = 10.0
STRIDE_S = 1.0
# Phase 3: per-feature window lengths.
# Pupil samples are dense (~120 Hz across both eyes) so 10s gives stable estimates.
# Fixations and blinks are sparse — 10s windows often have 0-2 events, making
# rates unstable. Use longer rolling windows for those feature groups while
# keeping predictions emitted every STRIDE_S seconds.
WINDOW_LEN_S_PUPIL = 10.0
WINDOW_LEN_S_FIXATION = 30.0
WINDOW_LEN_S_BLINK = 30.0  # was 60s; reduced to 30s — feature renamed `blink_rate_30s`
MIN_CONFIDENCE = 0.6
MIN_DATA_YIELD = 0.6
BASELINE_DURATION_S = 120.0
BLINK_LONG_THRESH_S = 0.5
BLINK_TRACKING_LOSS_S = 2.0
GAZE_GRID = (3, 3)

MATCH_OVERLAP_HIGH = 0.8
MATCH_OVERLAP_MIN = 0.5
MATCH_DURATION_RATIO_HIGH = (0.85, 1.15)
MATCH_DURATION_RATIO_OK = (0.7, 1.5)

STREAMING_FILENAME_TZ_OFFSET_HOURS = -6
STREAMING_FILENAME_TOLERANCE_S = 90.0
