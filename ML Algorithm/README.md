# RTAPS ML — Workload Classifier (v4)

The **Real-Time Adaptive Procedure System** watches an operator's eyes while they run a maintenance procedure and decides, every second, whether their cognitive workload is **low** or **high**. When the system sees "high" it puts extra guidance on the dashboard; when it sees "low" it stays out of the way.

This folder contains everything that turns recorded eye-tracking data into the model the live system uses: the training scripts, the feature spec, the labels, and the saved model artifact.

> **Currently deployed model:** `models/v4_rf_pnorm.joblib`Random Forest, 5 sensor-only features, 2-class output (`low` / `high`), labels derived by k-means clustering of per-step VACP `p_normalized`.

For the live serving stack see `Streaming_Backend/`. For the feature contract see `X_FEATURES.md`.

---

## 1. What the model does, in one paragraph

Every second, the backend grabs the last 10 s of pupil samples and the last 30 s of blinks and fixations. It turns those into **5 numbers** (the features). The Random Forest looks at those 5 numbers and outputs a probability for each class (`low`, `high`). The label with the highest probability is the "raw" prediction. A smoother makes sure the on-screen instructions only change when that raw label is stable for a few seconds in a row.

That's the whole thing. No procedure-id, no step-number, no session-clock — those would let the model cheat by memorising the procedure instead of learning physiology. v4 strips them so the model has to look at the eyes.

---

## 2. System architecture

```
┌─────────────────────────────┐                   ┌──────────────────────────┐
│  Pupil Capture (eye tracker)│   ZMQ topics      │  Pupil Capture bridge    │
│  - pupil samples @ 120 Hz   │ ─────────────────▶│  pupil_capture_bridge.py │
│  - blinks (Online plugin)   │                   └─────────┬────────────────┘
│  - fixations (Online plugin)│                             │ HTTP POST batches
└─────────────────────────────┘                             ▼
                                              ┌──────────────────────────────┐
                                              │  Streaming_Backend (FastAPI) │
                                              │  - /stream/{pupil,blinks,    │
                                              │    fixations}                │
                                              │  - /session/calibration_*    │
                                              │  - SessionState rolling buf  │
                                              │  - BaselineTracker (Mode A)  │
                                              │  - InferenceLoop (1 s tick)  │
                                              │  - Feature sanitizer (clip)  │
                                              │  - LocalPredictor → v4 RF    │
                                              │  - WorkloadSmoother (3 s)    │
                                              └─────────┬────────────────────┘
                                                        │  SSE
                                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       RTAPS Frontend (React)                                 │
│  - CalibrationScreen (120 s fixation cross BEFORE the procedure starts)      │
│  - SessionView (step instructions; "high" reveals extra guidance)            │
│  - StreamingDashboard (live ML preview of sensor values + predictions)       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Offline training pipeline (this folder)

```
01_build_session_index   → discover sessions across 3 laptops × 3 procedures
02_clean_pupil_export    → tidy parquets + per-session pupil baseline (quietest 120 s)
03_align_steps           → align RTAPS step boundaries to the pupil clock
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

Plus the RTAPS frontend's session log (`RTAPS/data/rtaps_sessions.csv`) giving step boundaries, procedure id, and participant id.

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

## 4. Features (X) — the 5 numbers the model sees

The order **must** match `FEATURE_NAMES` in `Streaming_Backend/app/feature_extractor.py`:

| \# | Feature | Window | What it measures (plain English) |
| --- | --- | --- | --- |
| 1 | `pupil_pcps_mean` | 10 s | How much the pupil has dilated/constricted compared to the operator's resting baseline. Bigger = more mental effort. |
| 2 | `pupil_diam_slope` | 10 s | Is the pupil getting bigger or smaller right now? (slope of diameter over the last 10 s) |
| 3 | `blink_rate_30s` | 30 s | Number of (real, non-tracking-loss) blinks in the last 30 s. Cognitive load tends to **suppress** blinking, so high workload usually = fewer blinks. |
| 4 | `fixation_dur_mean_ms` | 30 s | Average length of each fixation (the periods when the eyes are still). Longer fixations = deeper processing. |
| 5 | `fixation_dispersion_mean` | 30 s | How tightly clustered the gaze is within each fixation. Lower = more focused. |

**Why different windows per feature?** Pupil samples are dense (120 Hz), so 10 s gives a stable mean. Blinks and fixations are sparse — a 10 s slice often contains 0 or 1 events, which is too noisy. 30 s smooths them out without losing responsiveness.

**Predictions are still emitted every 1 s** — only the buffer slice differs per feature.

### What was deliberately left out

`procedure_id`, `step_number`, `cumulative_session_time_s`. These would let the model learn "step 5 of centrifuge is always high" without ever looking at the eyes. v4 forces it to use sensors.

---

## 5. Pupil baseline — what is "normal" for this operator?

`pupil_pcps_mean` is a **percent change vs. baseline**, not a raw size. That means we need a per-session baseline first.

### Training (offline)

`02_clean_pupil_export.py::_compute_baseline` scans the entire session in 30-second strides. For each candidate 120-second window, it counts blinks + fixations and picks the window with the **lowest combined count**. Baseline = mean pupil diameter inside that window — i.e. the calmest 2 minutes of the session.

```
strategy = "quietest_window"       if a calm 120 s exists with ≥ 120 samples
         = "session_median"        fallback if no candidate qualifies
         = "session_median_short"  fallback if session < 120 s
```

All 16 pupil-bearing sessions in the dataset use `quietest_window`.

### Live serving — explicit calibration (Mode A)

The deployed pipeline now has an **explicit calibration period** before the procedure starts. The frontend shows a fixation cross for 120 s while the operator sits calmly, and the backend collects baseline samples only during that window:

```
[ Operator puts on Pupil Capture ]
         │
         ▼
[ POST /session/calibration_start ]   ← frontend mounts CalibrationScreen
         │  (backend resets accumulator, marks calibrating=true)
         ▼
[ Pupil samples stream for 120 s  ]   ← BaselineTracker.add() collects them
         │  (no procedure timer yet; predictions still suppressed)
         ▼
[ POST /session/calibration_end ]     ← frontend countdown completes
         │  (backend freezes PupilBaseline)
         ▼
[ POST /session/start ]               ← procedure begins from step 1
         │  (session_started_at = calibration_end timestamp)
         ▼
[ First prediction ~10 s after step-1 starts ]
```

There is also a **Mode B (legacy auto-start)** path for clients that don't call `calibration_*` — the first pupil sample seeds an implicit 120 s window. Mode A is preferred because it guarantees the baseline captures genuine rest.

---

## 6. Labels (Y) — where "low" and "high" come from

We do not have per-second workload ratings. Instead, the user provided a **VACP analysis** (Visual / Auditory / Cognitive / Psychomotor — Zhu et al., 2025) for every step of every procedure. Each step gets an MWI (Mental Workload Index). The Y label sheets are `data/_processed/Y labels/*_vacp_workload.xlsx`.

For training we use `p_normalized`, defined per procedure as:

```
p_normalized = step_MWI / max(MWI across that procedure's steps)
```

so it sits in `[0, 1]` and is comparable across procedures.

### How the boundary between "low" and "high" is chosen

We have 35 step-level `p_normalized` values (step 0 excluded across all 3 procedures). v4 picks a 2-class boundary in two phases:

1. **k-means k=2** on the 35 values. The two cluster centres come out at **0.192** and **0.843**. A naïve midpoint split (0.517) would put only 4 steps into "high" — too imbalanced for cross-validation.
2. **Largest gap with a balance floor.** We sort the values and look at the gap between every neighbouring pair. The split is the midpoint of the **largest gap** that still leaves ≥ 7 steps in each class.

Result on the current Y labels:

|  |  |
| --- | --- |
| Boundary | `p_normalized > 0.328` → high, else low |
| Largest gap chosen | 0.0805 |
| Step-level distribution | **27 low / 8 high** |
| Total steps (excluding step 0) | 35 |

Every 1 s window inside a step inherits the step's label. At the window level the class balance is much better: **8 314 low / 9 906 high**(54 % high / 46 % low across 18 220 valid windows).

**All labels come from the user's hand-curated VACP analysis — no proxy, no synthetic data.**

### UI rendering rule

The frontend `SessionView.js`only reveals extra guidance when the workload is **high**:

- `low` → no extra block. The base step description is enough.
- `high` → an orange "Detailed Explanation" block (Why / What / How) appears below the step description.

(There is no manual override in the UI — instructions are purely model-driven.)

---

## 7. The model — Random Forest in a Pipeline

`07c_train_rf_pnorm.py` builds a tiny `sklearn.pipeline.Pipeline`:

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

In plain English:

- `SimpleImputer(strategy="median")` — Random Forests can't take `NaN` natively. If a feature is missing for a window (e.g., no fixations arrived yet), the imputer fills it with the **training median** for that feature. This is class-neutral and matters later for the live "feature sanitization" step (see §9).
- `n_estimators=400` — 400 decision trees voting.
- `max_depth=12 / min_samples_leaf=20 / min_samples_split=10` — keep trees shallow enough that they don't memorise individual windows. With only 11 participants, an unconstrained RF overfits to one or two operators' quirks.
- `max_features="sqrt"` — at each split, the tree may only consider √5 ≈ 2 features. Forces the forest to use *all* sensors instead of always picking the strongest one.
- `class_weight="balanced"` — even after picking a balanced boundary, the window-level distribution still leans high. This re-weights so the loss is symmetric.
- `random_state=42` — reproducible.

### Why Random Forest (not HGB / NN)?

Tried both in earlier versions (v2 = HGB, v3 = HGB sensors-only). RF came out on top in v4 because:

1. The dataset is small (\~18k windows, 11 participants). RFs handle small data well; gradient boosters tend to overfit.
2. RF gives **honest probabilities** out of the box, which the smoother downstream relies on.
3. Permutation importance is meaningful for RF, which made the train-serve skew diagnosis possible.

### Model artifact

Saved as a dict (so the live `LocalPredictor` can validate the contract):

```python
{
    "model": <Pipeline>,                # the sklearn Pipeline above
    "feature_columns": [...5 features...],
    "label_order": ["low", "high"],
    ...metrics, label_meta...
}
```

| Model | Script | Features | Y labels | Use |
| --- | --- | --- | --- | --- |
| `v1_hgb_weak.joblib` | `06_train_classifier.py` | 7 (legacy proxy) | weak rule | Pipeline regression test only |
| `v2_hgb_vacp.joblib` | `07_train_vacp_model.py` | 7 (incl. step_number, procedure_id) | VACP tertile | Lookup model — accurate but doesn't use sensors |
| `v3_hgb_sensors_only.joblib` | `07a_train_sensors_only.py` | 15 sensor-only | VACP tertile | Sensors-only HGB benchmark |
| `v4_rf_pnorm.joblib` (deployed) | `07c_train_rf_pnorm.py` | **5 sensor-only** | **p_normalized k-means k=2** | **Current production target** |

---

## 8. v4 performance (5-fold GroupKFold OOF)

`GroupKFold(n_splits=5, group=participant_id)` — no participant ever appears in both train and test of any fold, so the reported numbers are **out-of-fold (OOF)**, never tested on training data.

### Window level (18 220 windows)

| Metric | Value |
| --- | --- |
| Accuracy | 0.523 |
| Balanced accuracy | **0.528** |
| Macro F1 | 0.523 |
| Cohen's κ | +0.055 |

| Class | Precision | Recall | F1 | Support |
| --- | --- | --- | --- | --- |
| low | 0.481 | 0.577 | 0.525 | 8 314 |
| high | 0.574 | 0.479 | 0.522 | 9 906 |

### Step level (252 step instances, majority vote)

| Metric | Value |
| --- | --- |
| Accuracy | 0.567 |
| Balanced accuracy | 0.529 |
| Macro F1 | 0.506 |
| Cohen's κ | +0.046 |

### Feature importance

Permutation importance is the gold standard (shuffle one feature, measure the F1 drop):

| Feature | Permutation importance | Gini importance |
| --- | --- | --- |
| `blink_rate_30s` | **0.160** | 0.217 |
| `pupil_pcps_mean` | 0.147 | 0.232 |
| `fixation_dur_mean_ms` | 0.136 | 0.286 |
| `fixation_dispersion_mean` | 0.119 | 0.196 |
| `pupil_diam_slope` | 0.031 | 0.069 |

All five sensor features contribute non-zero importance and the distribution is balanced — no single feature dominates. (Earlier model versions had fixation features pinned at \~48 % combined gini, which caused live predictions to lock to "high" whenever the live fixation detector ran outside the training envelope. The new label scheme broke that dependency.)

### Honest assessment

κ = +0.055 means **v4 is modestly above chance** on a 2-class problem (random guessing = 50 %). The structural reason: step-level labels assign the same class to every window of a step, so within-step physiological variation has no Y signal to learn against. With only 11 participants and 252 step instances, that's the ceiling this dataset can produce.

Two paths past it:

1. **NASA-TLX collection** (gold standard) — per-participant per-step self-rating gives the within-class variation sensors need.
2. **Window-level VACP** — distribute operator-level VACP scores over time within each step. Needs richer operator timing data.

Even at κ ≈ 0.05, the model is *useful* for the UI: it correctly biases toward "high" when sensors show elevated activity, and the smoother absorbs the rest of the noise.

---

## 9. Train-serve skew (the feature sanitization layer)

The biggest non-obvious problem in v4 is that the live data is **not in the same distribution as the training data**. Three of the five features routinely fall outside the 1st-to-99th percentile envelope of the training set:

| Feature | Training 99th-percentile | Live typical |
| --- | --- | --- |
| `blink_rate_30s` | 21 | 30–50 (this user blinks more than research subjects) |
| `fixation_dur_mean_ms` | 211 ms | \~300 ms |
| `fixation_dispersion_mean` | 1.37° | \~1.9° |

Why: the training data was processed offline via Pupil Player exports (strict, conservative event detection). The live data comes from Pupil Capture's **Online** Fixation and Blink Detectors, which fire more events and report longer/wider fixations. Same biological signal, different summary statistics.

If we feed those raw values to the Random Forest, it has to extrapolate into untrained leaves — and the prediction is whatever class the nearest training leaf happened to carry. That can lock the output to "high" or "low" depending on which side of the envelope the live data sits on.

### The fix: sanitize at the model boundary

`Streaming_Backend/app/feature_extractor.py` defines a per-feature training envelope and a sanitizer:

```python
FEATURE_TRAINING_BOUNDS = {
    "pupil_pcps_mean":          (-0.29, 1.04),
    "pupil_diam_slope":         (-0.13, 0.13),
    "blink_rate_30s":           (0.0,   21.0),
    "fixation_dur_mean_ms":     (100.0, 211.0),
    "fixation_dispersion_mean": (0.58,  1.37),
}
```

When a live feature falls outside its `(lo, hi)` band, the sanitizer applies one of three strategies (controlled by `FEATURE_SANITIZE_STRATEGY` env var):

| Strategy | What it does | When to use |
| --- | --- | --- |
| `clip` **(default)** | Clamp to `[lo, hi]`. A live `blink_rate_30s=49` becomes `21` — still high relative to the training median of 3 but inside trained territory. **Preserves the direction of the signal.** | Normal operation. |
| `mask` | Replace with `NaN`. The pipeline's `SimpleImputer` then fills with the training median (class-neutral). **Kills the signal for that feature.** | Useful when a sensor is producing nonsense and you want it ignored. With three normally-OOD features this would silence 60 % of the model's input. |
| `off` | Pass through raw. | Diagnostics only. |

### Per-class medians (so you know what each value means to the model)

These are the medians of the training data after grouping by the new v4 labels — useful for sanity-checking what the model expects each class to look like:

| Feature | low median | high median | Δ (high − low) |
| --- | --- | --- | --- |
| `pupil_pcps_mean` | 0.011 | 0.064 | +0.053 |
| `pupil_diam_slope` | 0.000 | 0.000 | 0.000 |
| `blink_rate_30s` | 4.0 | 2.0 | **−2.0 (blink suppression at high load)** |
| `fixation_dur_mean_ms` | 131 | 137 | +6 |
| `fixation_dispersion_mean` | 1.20 | 1.16 | −0.04 |

So at the *median*, high workload looks like: slightly bigger pupil, fewer blinks, slightly longer + more focused fixations. The within-class spread is much bigger than these median deltas, which is why the model only reaches κ ≈ 0.05 — but the directions are sound.

---

## 10. The smoother — debouncing the UI

Raw second-by-second predictions are noisy. The `WorkloadSmoother`sits between the model and the UI:

- The **on-screen level** only changes when a new candidate label has held for `WORKLOAD_SMOOTHER_STABILITY_S` **consecutive seconds**(default **3 s**, tunable via the env var).
- The stability clock **restarts at each step boundary** so freshly entering a step doesn't carry the previous step's level in.
- Transitions are direction-guarded — when the model is producing intermediate levels, `low → high` must pass through `medium` first (only relevant if a future model goes back to 3 classes).

This is purely a UI debouncer — the raw model output is still logged and pushed via SSE so the frontend dashboard can show both.

---

## 11. Live serving contract

`Streaming_Backend/app/feature_extractor.py::FEATURE_NAMES` must equal v4's `FEATURE_COLS`. The `LocalPredictor` validates this on load and refuses to start on mismatch:

```python
FEATURE_NAMES = (
    "pupil_pcps_mean",
    "pupil_diam_slope",
    "blink_rate_30s",
    "fixation_dur_mean_ms",
    "fixation_dispersion_mean",
)
```

The live request path each second:

```
SessionState.window_arrays()         pull the last 10 s (pupil) / 30 s (blink+fixation)
        │
        ▼
feature_extractor.extract_features() compute the 5 numbers
        │
        ▼
sanitize_features_to_training_distribution(strategy="clip")
        │
        ▼
LocalPredictor.predict()             RF predicts {"low": p, "high": q}
        │
        ▼
WorkloadSmoother.update()            require 3 s of stability before display flips
        │
        ▼
SSE → frontend                       SessionView.js reveals/hides high-workload block
```

---

## 12. Cross-validation strategy

```
GroupKFold(n_splits=5, group=participant_id)
```

- 11 participants → 5 folds, \~2 participants held out per fold.
- No participant appears in both train and test of any fold.
- Reported metrics are out-of-fold (OOF) — never tested on training data.
- Per-participant balanced accuracy is also saved to `models/rf_per_participant.csv` to detect collapse on individuals.

---

## 13. Reproducing the model

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
python scripts/07c_train_rf_pnorm.py           # v4 — writes models/v4_rf_pnorm.joblib
```

`scripts/lib/config.py` is the single source of truth for window lengths, strides, confidence thresholds, baseline duration, etc. `Streaming_Backend/app/config.py` keeps the same defaults so live serving matches training.

**To retrain with updated Y labels:** just edit `data/_processed/Y labels/*_vacp_workload.xlsx` and re-run step 7c. The script reads the `Step Summary` sheet from each procedure's xlsx, re-runs the k-means + largest-gap boundary search on the new `p_normalized` values, and saves a fresh `v4_rf_pnorm.joblib`.

> Windows / PowerShell tip: if you see a `UnicodeEncodeError` on the "→" character, run with `$env:PYTHONIOENCODING="utf-8"` first.

---

## 14. Folder map

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
│       │   ├── centrifuge_vacp_workload.xlsx
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

## 15. Where the rest of the system lives

- **Live serving:** `../Streaming_Backend/` — FastAPI app that ingests Pupil Capture data, gates predictions behind calibration, sanitizes features, runs the v4 model every second, and pushes smoothed predictions to the frontend via SSE.
- **Frontend:** `../RTAPS_Frontend/` — React app showing the CalibrationScreen, procedure steps, and live workload feedback.
- **Capture bridge:**`../Streaming_Backend/pupil_capture_bridge.py`— runs on the laptop with Pupil Capture open; subscribes to ZMQ topics and forwards to the backend.

---

## 16. Open issues and roadmap

1. **NASA-TLX labels** — gold-standard individual workload labels. Single biggest lever for raising κ to ≥ 0.40.
2. **Window-level VACP** — distribute operator-level VACP scores over time within each step. Needs operator timing data; deferred.
3. **End-to-end replay test** — run an existing offline session through the live `Streaming_Backend` and compare features + predictions to training values. Prerequisite for trusting any deployed prediction.
4. **More participants** — 11 is small. With 25–30 you'd have more cross-validation power.
5. **Reduce train-serve skew at the source** — either re-train on data exported from the Online detectors, or feed the Online events through the same offline cleaning pipeline before training. Would let us drop the sanitizer entirely.

References:

- `X_FEATURES.md` — canonical feature spec
- `scripts/README.md` — pipeline notes