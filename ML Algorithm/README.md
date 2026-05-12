# RTAPS ML — Workload Classifier (v4)

End-to-end pipeline for the **Real-Time Adaptive Procedure System** workload
classifier. Eye-tracking signals (pupil, blinks, fixations) recorded while
operators perform three procedures (Centrifuge, Column Flushing, Pressure
Testing) are turned into per-second predictions of cognitive workload
(`low` / `medium` / `high`), which the live dashboard consumes to adapt the
on-screen instructions.

This README is the deep dive — for the feature contract see
[`X_FEATURES.md`](X_FEATURES.md), and for the live serving stack see
[`Streaming_Backend/`](../Streaming_Backend/).

**Current deployed model: `v4_rf_pnorm.joblib`** (Random Forest, sensor-only
inputs, labels from k-means clustering of per-step VACP `p_normalized`).

---

## 1. Problem statement

Predict the operator's **cognitive workload level** (low / medium / high) for
the *current* procedure step, in real time, every second, using **only**
eye-tracking signals:

- last **10 s** of pupil samples (60 Hz/eye) for pupil dilation and slope
- last **30 s** of fixations for visual processing depth
- last **30 s** of blinks for cognitive blink suppression

No `step_number`, no `procedure_id`, no session-clock features — those let
the model fall back on a deterministic step-number lookup instead of learning
from physiology. v4 strips them so the model is forced to use sensors.

Output drives a smoothed instruction display (Low / Medium / High) via the
`WorkloadSmoother` in the streaming backend. Low workload shows no extra
guidance — the base step description is enough.

---

## 2. Architecture overview

```
┌─────────────────────────────┐                   ┌──────────────────────────┐
│  Pupil Capture (eye tracker)│   ZMQ topics      │  Pupil Capture bridge    │
│  - pupil samples @ 120 Hz   │ ─────────────────▶│  pupil_capture_bridge.py │
│  - blinks (Online plugin)   │                   └─────────┬────────────────┘
│  - fixations (Online plugin)│                             │  HTTP POST batches
└─────────────────────────────┘                             ▼
                                                ┌──────────────────────────────┐
                                                │  Streaming_Backend (FastAPI) │
                                                │  - /stream/pupil  /blinks    │
                                                │    /fixations                │
                                                │  - /session/calibration_*    │
                                                │  - SessionState rolling buf  │
                                                │  - BaselineTracker (Mode A)  │
                                                │  - InferenceLoop (1 s tick)  │
                                                │  - WorkloadSmoother (30 s)   │
                                                │  - LocalPredictor → v4 RF    │
                                                └─────────┬────────────────────┘
                                                          │  SSE
                                                          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       RTAPS Frontend (React)                                 │
│  - CalibrationScreen (120 s fixation cross BEFORE the procedure starts)      │
│  - SessionView (step instructions; medium → high cumulative display)         │
│  - StreamingDashboard (live ML preview of sensor values + predictions)       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Offline training pipeline (this folder)

```
01_build_session_index   → discover sessions across 3 laptops × 3 procedures
02_clean_pupil_export    → tidy parquets + per-session pupil baseline (quietest 120 s)
03_align_steps           → align RTAPS step boundaries to pupil clock
04_extract_features      → 1 s decision grid → per-window feature rows
                           (pupil 10 s window, fixation 30 s, blink 30 s)
04b_add_normalized       → adds per-participant (_zp) and per-procedure (_zproc) z-scores
05_summarize_per_step    → per-step QA aggregates
06_train_classifier      → (legacy) weak proxy labels — kept as regression test only
07_train_vacp_model      → (v2) VACP-tertile labels + step/procedure features → lookup model
07a_train_sensors_only   → (v3) VACP-tertile labels, sensor-only X
07c_train_rf_pnorm       → (v4 current) Random Forest, p_normalized k-means Y, sensor-only X
```

---

## 3. Data flow

### Raw inputs (per session)
```
data/<Laptop>/Model_data/<User_NN_Procedure>/
  ├── pupil_positions.csv     # offline export (preferred)
  ├── blinks.csv              # Online Blink Detector
  ├── fixations.csv           # Online Fixation Detector
  ├── gaze_positions.csv      # 2D gaze (kept but not used)
  └── world_timestamps.npy    # for clock anchoring
```
Plus the RTAPS frontend's session log (`RTAPS/data/rtaps_sessions.csv`)
giving step boundaries, procedure id, and participant id.

### Processed outputs
```
data/_processed/
  ├── session_index.csv         # 1 row per discovered session
  ├── procedure_steps.csv       # canonical step list per procedure
  ├── baselines.csv             # per-session pupil baseline (quietest 120 s window)
  ├── data_quality.csv          # sample counts, rates, yields
  ├── step_alignment_summary.csv
  ├── X_window_summary.csv
  ├── feature_dictionary.md     # generated by stage 04
  ├── Y labels/                 # VACP workload analysis (Excel, 3 procedures)
  │   ├── *_vacp_workload.xlsx  # 3 sheets each:
  │   │   ├── Operators         # per-operator VACP rows
  │   │   ├── Legend & VACP     # weight reference (Zhu et al., 2025)
  │   │   └── Step Summary      # per-step MWI + p_normalized (Y source for v4)
  └── {centrifuge,column_flushing,pressure_testing}/
      ├── X_window.parquet      # primary training table
      ├── X_step.parquet        # per-step aggregates
      └── per_session/<sid>/    # cleaned tidy parquets (gitignored)
```

---

## 4. Features (X) — the v4 contract

**5 sensor-only features.** Order MUST match
[`Streaming_Backend/app/feature_extractor.py`](../Streaming_Backend/app/feature_extractor.py)
`FEATURE_NAMES`:

| # | Feature | Window | Source | What it measures |
|---|---|---|---|---|
| 1 | `pupil_pcps_mean` | 10 s | pupil samples + per-session baseline | % change in pupil size vs. participant baseline (PCPS) |
| 2 | `pupil_diam_slope` | 10 s | pupil samples (diameter vs. timestamp) | Within-window pupil dilation/constriction rate |
| 3 | **`blink_rate_30s`** | **30 s** | blink onset events | Count of (non-tracking-loss) blinks in the last 30 s |
| 4 | `fixation_dur_mean_ms` | 30 s | fixation events | Mean fixation duration in ms |
| 5 | `fixation_dispersion_mean` | 30 s | fixation events | Within-fixation spatial jitter |

**Important rename (v4):** `blink_rate_per_min` (60 s window, extrapolated to
/min) → `blink_rate_30s` (raw count over a 30 s window). Reflected in
[lib/blink_features.py](scripts/lib/blink_features.py), [lib/config.py](scripts/lib/config.py),
[04_extract_features_window.py](scripts/04_extract_features_window.py),
[04b_add_normalized_features.py](scripts/04b_add_normalized_features.py),
[Streaming_Backend/app/feature_extractor.py](../Streaming_Backend/app/feature_extractor.py),
and [RTAPS_Frontend/src/pages/StreamingDashboard.js](../RTAPS_Frontend/src/pages/StreamingDashboard.js).

**What was removed from v3 → v4:** `procedure_id`, `step_number`,
`cumulative_session_time_s`. These let the model bypass physiology and use
a deterministic lookup — explicitly removed so v4 has to do real work.

### Per-feature window lengths (Phase 3 finding)

Pupil samples are dense (~120 Hz across both eyes), so 10 s gives a stable
mean. Fixations and blinks are sparse — a 10 s window often contains 0–2
events, giving noisy rates. v4 uses:

- **10 s** for pupil features (responsive)
- **30 s** for fixation features (stable)
- **30 s** for blink rate (was 60 s in v3; user reduced to 30 s for v4)

Predictions are still emitted every 1 s; only the buffer slice differs.

---

## 5. Pupil baseline strategy

### Training (offline)

`02_clean_pupil_export.py::_compute_baseline` scans the entire session in
30-second strides. For each candidate 120-second window, it counts blinks +
fixations and picks the window with the lowest combined count. Baseline =
mean pupil diameter inside that window.

```
strategy = "quietest_window"       if a calm 120 s exists with ≥ 120 samples
         = "session_median"        fallback if no candidate qualifies
         = "session_median_short"  fallback if session < 120 s
```

All 16 pupil-bearing sessions in the current dataset use `quietest_window`.

### Live serving — calibration phase (NEW in v4)

The deployed pipeline now has an **explicit calibration period** before the
procedure starts. The frontend shows a fixation cross for 120 seconds while
the operator sits calmly; the backend's `BaselineTracker` runs in **Mode A
(explicit calibration)** and accumulates samples only during that window:

```
[ Operator puts on Pupil Capture ]
         │
         ▼
[ POST /session/calibration_start ]      ← frontend mounts CalibrationScreen
         │  (backend resets accumulator, marks calibrating=true)
         ▼
[ Pupil samples stream for 120 s  ]      ← BaselineTracker.add() collects them
         │  (no procedure timer yet; predictions still suppressed)
         ▼
[ POST /session/calibration_end ]        ← frontend countdown completes
         │  (backend freezes PupilBaseline)
         ▼
[ POST /session/start ]                  ← procedure begins from step 1
         │  (session_started_at = calibration_end timestamp)
         ▼
[ First prediction emitted after 10 s of step-1 data ]
```

The backend also keeps a **Mode B (legacy auto-start)** code path for
backwards compatibility with older clients that don't call `calibration_*`
endpoints — in that case the first pupil sample seeds an implicit 120 s
calibration window. Mode A is preferred because it guarantees the baseline
captures rest (no task work).

---

## 6. Labels (Y) — `p_normalized` clustering

`p_normalized` is the per-step VACP MWI normalized to the procedure's max
MWI (range 0–1). Computed and stored in each procedure's
`Step Summary` sheet:

```
p_normalized = step_VACP_total / max(step_VACP_total across that procedure's steps)
```

v4 uses **k-means with k=3** on the 35 step-level `p_normalized` values
(step 0 excluded across all 3 procedures) to find the natural breakpoints
between low / medium / high workload:

- **Cluster centers:** 0.117, 0.299, 0.845
- **Boundaries:** `low ≤ 0.208`, `medium ≤ 0.572`, `high > 0.572`
- **Step-level class distribution:** 16 low, 15 medium, 4 high

Every 1 s window inherits its step's label. **All labels come from the user's
hand-curated VACP analysis — no proxy, no fake data.**

### UI rendering rule

The frontend [SessionView.js](../RTAPS_Frontend/src/pages/SessionView.js) only
renders extra guidance when the workload reaches medium or high. **Low →
nothing shown** (the base step description is enough). When the level
escalates within a step (e.g., medium → high), the previous medium block
stays visible and the new high block is added on top (cumulative).

---

## 7. Model — Random Forest

`07c_train_rf_pnorm.py` builds a `sklearn.pipeline.Pipeline`:

```python
Pipeline([
    ("impute", SimpleImputer(strategy="median")),
    ("rf", RandomForestClassifier(
        n_estimators=400,
        max_depth=12,
        min_samples_leaf=20,
        min_samples_split=10,
        max_features="sqrt",
        class_weight="balanced",
        n_jobs=-1,
        random_state=42,
    )),
])
```

- **`SimpleImputer`** handles NaN sensor values (RF can't take NaN natively).
- **`class_weight="balanced"`** compensates for the skew toward "low" /
  "high" classes (medium is the smallest).
- **5-fold `GroupKFold`** over 11 participants — no participant ever
  appears in both train and test of any fold.

| Model | Script | Features | Y labels | Use |
|---|---|---|---|---|
| `v1_hgb_weak.joblib` | `06_train_classifier.py` | 7 (legacy proxy labels) | weak rule | Pipeline regression test only |
| `v2_hgb_vacp.joblib` | `07_train_vacp_model.py` | 7 (incl. step_number, procedure_id) | VACP tertile | Lookup model — accurate but doesn't use sensors |
| `v3_hgb_sensors_only.joblib` | `07a_train_sensors_only.py` | 15 sensor-only | VACP tertile | Sensors-only HGB benchmark |
| **`v4_rf_pnorm.joblib`** (deployed) | **`07c_train_rf_pnorm.py`** | **5 sensor-only** | **p_normalized k-means** | **Current production target** |

---

## 8. v4 metrics (5-fold GroupKFold OOF)

| Level | Accuracy | Balanced Acc | Macro F1 | Cohen's κ |
|---|---|---|---|---|
| Window | 0.361 | 0.337 | 0.338 | +0.023 |
| Step (majority) | 0.317 | 0.341 | 0.295 | −0.024 |

Per-class F1: low 0.40 / medium 0.18 / high 0.43.

**Feature importance (permutation, on F1-macro):**

| Feature | Permutation Importance |
|---|---|
| `blink_rate_30s` | **0.227** |
| `pupil_pcps_mean` | 0.207 |
| `fixation_dur_mean_ms` | 0.184 |
| `fixation_dispersion_mean` | 0.152 |
| `pupil_diam_slope` | 0.028 |

All five sensor features contribute non-zero importance — sensors are
**actually being used** (vs. v2 where they were 0%).

### Honest assessment

κ = +0.023 means **v4 is barely above chance** on a 3-class problem (random
guessing = 33%). The structural reason: step-level labels assign the same
class to every window of a step, so within-step physiological variation has
no Y signal to learn against. With only 11 participants, that's the ceiling
this dataset can produce. Two paths past it:

1. **NASA-TLX collection** (gold standard) — per-participant per-step rating
   gives the within-class variation sensors need.
2. **Window-level VACP** — partial fix, needs richer operator timing data.

Until then, v4 is best deployed *alongside* v2 (lookup) as a sensor-anomaly
monitor, not as the primary instruction driver. The current deployment in
`Streaming_Backend/app/config.py` points to v4 for development; in
production this can be swapped to v2 by setting `MODEL_PATH` env var.

---

## 9. Cross-validation strategy

```
GroupKFold(n_splits=5, group=participant_id)
```

- 11 participants → 5 folds, ~2 participants held out per fold
- No participant appears in both train and test of any fold
- Reported metrics are out-of-fold (OOF) — never tested on training data
- Per-participant balanced accuracy is also reported in
  `models/rf_per_participant.csv` to detect collapse on individuals

---

## 10. Pipeline reproducibility

```bash
cd "ML Algorithm"
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt

# Place raw data under data/{Dr_Zahabi_laptop, Lenovo_laptop, Loaner_laptop}
python scripts/01_build_session_index.py
python scripts/02_clean_pupil_export.py        # quietest-120s baseline
python scripts/03_align_steps.py
python scripts/04_extract_features_window.py   # per-feature windows (pupil 10s, fix 30s, blink 30s)
python scripts/04b_add_normalized_features.py  # _zp and _zproc features
python scripts/05_summarize_per_step.py
python scripts/07c_train_rf_pnorm.py           # v4 — current production target
```

`scripts/lib/config.py` is the single source of truth for window lengths,
strides, confidence thresholds, baseline duration, etc. The
`Streaming_Backend/app/config.py` keeps the same defaults so live serving
matches training.

---

## 11. Live serving contract

`Streaming_Backend/app/feature_extractor.py::FEATURE_NAMES` must equal v4's
`FEATURE_COLS`. The `LocalPredictor` validates this on load and refuses to
start on mismatch:

```python
# Training-time and serving-time MUST agree:
FEATURE_NAMES = (
    "pupil_pcps_mean",
    "pupil_diam_slope",
    "blink_rate_30s",
    "fixation_dur_mean_ms",
    "fixation_dispersion_mean",
)
```

`WorkloadSmoother` (30 s stability window + direction guard) handles
instruction-display stability so the on-screen feedback doesn't flip every
second between low/medium/high. See
[Streaming_Backend/app/workload_smoother.py](../Streaming_Backend/app/workload_smoother.py).

---

## 12. Folder map

```
ML Algorithm/
├── README.md                  # this file
├── X_FEATURES.md              # canonical feature spec (X side)
├── scripts/
│   ├── 00_make_weak_labels.py        # (legacy) proxy labels for v1
│   ├── 01_build_session_index.py
│   ├── 02_clean_pupil_export.py      # tidy parquets + quietest-120s baseline
│   ├── 03_align_steps.py
│   ├── 04_extract_features_window.py # per-feature windows
│   ├── 04b_add_normalized_features.py # _zp / _zproc z-scores
│   ├── 05_summarize_per_step.py
│   ├── 06_train_classifier.py        # v1 — weak labels (legacy)
│   ├── 07_train_vacp_model.py        # v2 — VACP labels, full features (lookup)
│   ├── 07a_train_sensors_only.py     # v3 — sensors only (HGB)
│   ├── 07c_train_rf_pnorm.py         # v4 — RF + p_normalized k-means (current)
│   ├── lib/                          # shared modules
│   │   ├── config.py                 # window lengths, thresholds
│   │   ├── pupil_features.py
│   │   ├── blink_features.py
│   │   ├── fixation_features.py
│   │   ├── gaze_features.py
│   │   ├── task_features.py
│   │   ├── sync.py                   # clock anchoring
│   │   ├── procedures_parser.py
│   │   └── io_utils.py
│   ├── requirements.txt
│   └── README.md                     # detailed pipeline notes
├── data/
│   ├── Dr_Zahabi_laptop/             # raw exports (gitignored)
│   ├── Lenovo_laptop/
│   ├── Loaner_laptop/
│   └── _processed/                   # derived; small QA artifacts committed
│       ├── session_index.csv
│       ├── procedure_steps.csv
│       ├── baselines.csv             # includes baseline_strategy column
│       ├── data_quality.csv
│       ├── feature_dictionary.md
│       ├── Y labels/
│       │   ├── centrifuge_vacp_workload.xlsx     # 3 sheets each
│       │   ├── column_flushing_vacp_workload.xlsx
│       │   └── pressure_testing_vacp_workload.xlsx
│       └── {centrifuge,column_flushing,pressure_testing}/
│           ├── X_window.parquet
│           ├── X_step.parquet
│           └── per_session/<sid>/    (gitignored)
└── models/
    ├── v1_hgb_weak.joblib            # (legacy)
    ├── v2_hgb_vacp.joblib            # lookup model (VACP labels)
    ├── v3_hgb_sensors_only.joblib    # sensors-only HGB
    ├── v4_rf_pnorm.joblib            # CURRENT — sensor-only RF, p_normalized labels
    ├── rf_cv_metrics.json            # v4 metrics
    ├── rf_feature_importance.csv
    ├── rf_oof_window.parquet
    ├── rf_oof_step.parquet
    ├── rf_confusion_window.csv
    ├── rf_confusion_step.csv
    └── rf_per_participant.csv
```

---

## 13. Where the rest of the system lives

- Live serving: [`../Streaming_Backend/`](../Streaming_Backend/) — FastAPI app
  that ingests Pupil Capture data, gates predictions behind calibration,
  runs the v4 model every second, and pushes smoothed predictions to the
  frontend via SSE.
- Frontend: [`../RTAPS_Frontend/`](../RTAPS_Frontend/) — React app showing
  the CalibrationScreen, procedure steps, and live workload feedback.
- Capture bridge: [`../Streaming_Backend/pupil_capture_bridge.py`](../Streaming_Backend/pupil_capture_bridge.py)
  — runs on the laptop with Pupil Capture open; subscribes to ZMQ topics
  and forwards to the backend.

---

## 14. Open issues and roadmap

1. **NASA-TLX labels** — gold-standard individual workload labels.
   Single biggest lever for raising κ to ≥ 0.40.
2. **Window-level VACP** — distribute operator-level VACP scores
   over time within each step. Needs operator timing data; deferred.
3. **End-to-end replay test** — run an existing offline session through the
   live `Streaming_Backend` and compare features + predictions to training
   values. Prerequisite for trusting any deployed prediction.
4. **More participants** — 11 is small. With 25-30 you'd have more cross-
   validation power.

References:
- [`X_FEATURES.md`](X_FEATURES.md) — canonical feature spec
- [`scripts/README.md`](scripts/README.md) — pipeline notes
- [`/Users/user/.claude/plans/does-this-means-that-peaceful-pixel.md`](../../.claude/plans/does-this-means-that-peaceful-pixel.md) — multi-phase X→Y strengthening plan
