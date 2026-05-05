# RTAPS dataset build pipeline

Builds the per-window training table `X_window.parquet` for the RTAPS workload
classifier. Five sequential stages, each with one job and an inspectable
artifact, written under `ML Algorithm/data/_processed/`.

## Pipeline at a glance

```
01_build_session_index.py  ->  session_index.csv, procedure_steps.csv
02_clean_pupil_export.py   ->  per_session/*.parquet, baselines.csv, data_quality.csv
03_align_steps.py          ->  per_session/step_boundaries.parquet, step_alignment_summary.csv
04_extract_features_window ->  X_window.parquet, X_window_sample.csv, feature_dictionary.md
05_summarize_per_step.py   ->  X_step.parquet (QA aggregation)

00_make_weak_labels.py     ->  labels_weak.csv  (proxy Y; required by stage 4 + 6)
06_train_classifier.py     ->  models/v1_hgb_weak.joblib + cv_metrics.json + ...
```

Stages 01–05 build the X table. Stage 00 builds the (proxy) Y table. Stage 06
trains the model on the **8-feature contract** defined in `../X_FEATURES.md`.

## Setup

```bash
cd "ML Algorithm"
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt
```

## Run

```bash
# X side
python scripts/01_build_session_index.py
python scripts/02_clean_pupil_export.py
python scripts/03_align_steps.py

# Y side (proxy labels — replace with NASA-TLX / SOA when available)
python scripts/00_make_weak_labels.py

# Join X + Y, then train
python scripts/04_extract_features_window.py \
    --labels_csv data/_processed/labels_weak.csv
python scripts/05_summarize_per_step.py
python scripts/06_train_classifier.py
```

Stages are idempotent — re-running overwrites outputs.

## Output layout

```
ML Algorithm/data/_processed/
├── session_index.csv                # master catalog (1 row per recording)
├── procedure_steps.csv              # (procedure_id, step_id, step_number, time_threshold_s)
├── baselines.csv                    # per-session pupil baseline (mean of first 60 s)
├── data_quality.csv                 # per-session pupil rate, yields, file presence
├── step_alignment_summary.csv       # per-session UI ↔ Pupil offsets (sanity)
├── X_window_summary.csv             # per-session row counts at stage 4
├── feature_dictionary.md            # one row per feature: formula, units, deploy_feasible
│
├── pressure_testing/
│   ├── X_window.parquet             # PRIMARY training X (one row per causal 10s window)
│   ├── X_window_sample.csv          # 5 % stratified sample for eyeballing
│   ├── X_step.parquet               # mean/std/median per (session, step)
│   └── per_session/
│       └── <session_uid>/
│           ├── pupil_clean.parquet  # synced_t, unix_t, eye_id, diameter_mm, confidence, source
│           ├── fixations_clean.parquet
│           ├── blinks_clean.parquet
│           ├── gaze_clean.parquet
│           └── step_boundaries.parquet  # one row per UI step in synced_t and unix_t
├── centrifuge/        ... same structure ...
└── column_flushing/   ... same structure ...
```

`X_window.parquet` carries ~50 columns (the historical kitchen-sink feature
set); `06_train_classifier.py` selects ONLY the 8 columns listed in
`X_FEATURES.md`. Treat the rest as QA / future-feature scratch space.

## Joining workload labels

`X_window.parquet` ships with `workload_label` as `NA`. To attach labels later,
provide a CSV with columns `(session_uid, step_number, workload_label)` and run
stage 4 with `--labels_csv path/to/labels.csv`. Stage 5 will then carry the
label through to `X_step.parquet` automatically.

For now stage 0 generates a proxy `labels_weak.csv` from
`exceededThreshold + subStepsShown` so the rest of the pipeline can run
end-to-end. **This is a pipeline test, not a real training signal** — see
`../X_FEATURES.md` §9 for the Y-label gap.

## Training (stage 6)

`06_train_classifier.py` is the only place the model contract is exercised.
It hard-codes the 8 features from `../X_FEATURES.md` and refuses to consume
anything else from `X_window.parquet`. Cross-validation is `GroupKFold` over
`participant_id` so the same person's data never appears in both train and
test.

Outputs (under `../models/`):

| file | what |
|---|---|
| `v1_hgb_weak.joblib` | fitted final model + feature column list + label order |
| `cv_metrics.json` | per-fold and aggregate macro-F1 / balanced-acc / accuracy |
| `oof_predictions_window.parquet` | OOF preds at the window level |
| `oof_predictions_step.parquet` | OOF preds aggregated to step level (majority vote) |
| `feature_importance.csv` | permutation importance (macro-F1 scoring) on the refit model |
| `confusion_matrix_window.csv` | window-level confusion matrix (3×3) |
| `confusion_matrix_step.csv` | step-level confusion matrix (3×3) |

## Key design choices

- **Sample unit**: causal 10 s sliding window, stride 1 s (final stage). Predictions
  are made *while* the operator is doing a step; multiple in-step predictions
  feed a downstream feedback policy (out of scope here).
- **Procedures, not laptops**, as the directory hierarchy. The `laptop` field is
  preserved as a column on `session_index.csv` for traceability and per-laptop QA.
- **Time sync via Pupil's `synced_s` clock** as the canonical timeline. UTC
  (`unix_t`) is materialized on every parquet for joining with the RTAPS UI
  step log.
- **Pupil source priority**: prefer offline `pupil_positions.csv` (with the
  `pye3d` 3D-pupil estimates) over the streaming `pupil_data_*.csv` (which is
  what the live system would emit). Either path produces the same schema.

## Notes about the source data (read once)

- The `S<XXX>/T<YYY>` folder naming under `Streaming_data/` does **not**
  correspond to `User_<XXX>` under `Model_Data/`. Pairing is by laptop +
  filename UTC time, not by name. Stage 1 prints any pairings whose match
  confidence is below `high` for hand-review.
- Pupil `pupil_positions.csv` contains both `2d c++` and `pye3d 0.3.0 real-time`
  rows for every sample; we keep only the `pye3d` rows because they carry
  `diameter_3d` (in mm). The streaming CSV duplicates each timestamp with a
  `diameter == 0` placeholder for the `2d c++` method; we drop those.
- Fixation `duration` in `fixations.csv` is in **milliseconds**.
- Blink `duration` in `blinks.csv` is in **seconds**. Blinks longer than
  `BLINK_TRACKING_LOSS_S` (default 2 s) are flagged `tracking_loss=True` and
  excluded from blink-rate features downstream.
- A handful of sessions are missing `pupil_positions.csv` (≈ 8/24) or
  `fixations.csv` (≈ 2/24). The pipeline emits whatever is available; the
  featurizer at stage 4 will skip features whose source is missing rather than
  fail the row.

## Configuration

All knobs live in `scripts/lib/config.py`:

| Name | Default | Used by |
|---|---|---|
| `WINDOW_LEN_S` | 10.0 | stage 4 |
| `STRIDE_S` | 1.0 | stage 4 |
| `MIN_CONFIDENCE` | 0.6 | stage 2 |
| `MIN_DATA_YIELD` | 0.6 | stage 4 |
| `BASELINE_DURATION_S` | 60.0 | stage 2 |
| `BLINK_LONG_THRESH_S` | 0.5 | stage 4 |
| `BLINK_TRACKING_LOSS_S` | 2.0 | stage 2 |
| `GAZE_GRID` | (3, 3) | stage 4 |
| `MATCH_OVERLAP_HIGH` | 0.8 | stage 1 (high-confidence threshold) |
| `MATCH_OVERLAP_MIN` | 0.5 | stage 1 (min overlap to keep) |
| `STREAMING_FILENAME_TZ_OFFSET_HOURS` | -6 | stage 1 (CST = UTC-6) |
| `STREAMING_FILENAME_TOLERANCE_S` | 90.0 | stage 1 (Pupil↔streaming CSV pairing) |

## QA gates after each stage

1. **Stage 1** (`session_index.csv`): inspect `match_confidence`. Expect ≥ 80 %
   `high`. Anything `medium`/`low`/`UNMATCHED` is printed at the end of the run.
2. **Stage 2** (`data_quality.csv`): per-eye pupil rate should be 30–80 Hz for
   each session that has pupil data. Sessions with **no** pupil **and no**
   fixations are flagged — these can't be featurized and will be dropped at
   stage 4.
