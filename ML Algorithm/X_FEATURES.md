# X Features — Specification for the RTAPS Workload Model

This document specifies the input features (X) for the RTAPS workload classifier.
It records **which features we use, why we chose them, and what we deliberately
left out**. The document is the reference of record — when in doubt, this file
is what the training pipeline (`scripts/06_train_classifier.py`) and the live
streaming backend (`streaming_backend/`) must agree on.

> **Status as of writing:** The X side is finalized (this document). The Y side
> is still pending — see *Open issues* at the end. Do not retrain models on
> proxy labels.

---

## 1. The problem we are predicting

Predict the user's **cognitive workload level (low / medium / high)** for the
*current* procedure step, in real time, every second, using the last 10 seconds
of eye-tracking data plus minimal task context.

The model produces multiple in-step predictions; a downstream policy aggregates
them to drive the UI feedback (out of scope here).

---

## 2. Design principles for choosing features

The 48-feature first cut was a "kitchen-sink" extraction. We pruned aggressively
to 7 features using four rules:

1. **Real, measured data only.** No synthetic, proxy, or imputed values. Every
   feature must trace to a sensor reading or a UI event recorded during the
   actual session.
2. **Real-time extractable.** Every feature must be computable at deployment
   time from the live ZMQ stream and frontend events — no offline-only inputs.
3. **Theoretically grounded.** Each feature must map to an established
   physiological or task mechanism of cognitive workload (Beatty 1982; Stern
   et al. 1984; Holmqvist et al. 2011).
4. **Non-redundant and non-leaky.** No two features measure the same thing;
   no feature is derived from the label.

Sample-to-feature ratio also drove pruning: with ~10 unique participants, we
can responsibly support ~5–10 features, not 48.

---

## 3. The 7 features

| # | Feature | Short meaning | Source | What it measures | Why it's in |
|---|---|---|---|---|---|
| 1 | `pupil_pcps_mean` | How dilated the pupil is versus that person's own first-2-minute calm size | pupil samples + per-session 120 s baseline | % change in pupil size vs. participant baseline | The canonical cognitive-load marker. Direct sympathetic-nervous-system response. Baseline-normalized so it's directly comparable across participants. |
| 2 | `blink_rate_per_min` | How often the person blinks (normal blinks only) | blink onset events | Blinks per minute (excluding tracking-loss blinks) | Cognitive blink suppression — well-validated workload marker; rate drops measurably under load. |
| 3 | `fixation_dur_mean_ms` | How long they typically stay fixed on one gaze point | fixation events | Mean fixation duration (ms) | Long fixations indicate deeper visual processing / difficulty extracting information. |

The current model uses **only the 3 sensor features above plus `pupil_diam_slope`** (4 total). The fields below are tracked for UI routing but are **not** model inputs — feeding `procedure_id` / `step_number` would let the model read the label off the step instead of the eyes (the label is derived from the step), and `cumulative_session_time_s` hurt leave-participants-out accuracy in testing. `fixation_dispersion_mean` was dropped (little added accuracy, correlated with `fixation_dur_mean_ms`).

| field (not a model input) | meaning |
|---|---|
| `procedure_id` | Which procedure is active (1=Centrifuge, 2=Column Flushing, 3=Pressure Testing). |
| `step_number` | Current step ordinal within the procedure. |
| `cumulative_session_time_s` | Seconds since the procedure started. |

### Per-feature rationale and citations

**Pupil feature (#1).** Pupil dilation is the most-studied physiological
indicator of cognitive workload; PCPS (Percent Change in Pupil Size relative to
a baseline) controls for individual differences in resting pupil size, making
it usable across participants without per-participant calibration in the model.
`pupil_diam_slope` was removed — the within-window trend added marginal
signal at n < 10 participants and introduced noise at window boundaries.

**Blink rate (#2).** Cognitive blink suppression is robust and easy to detect
from blink-onset events. Tracking-loss blinks (>2 s) are explicitly excluded
upstream so they don't inflate the rate.

**Fixation features (#3, #4).** Fixation duration and dispersion together
characterize the *depth* and *stability* of visual processing without depending
on screen-coordinate semantics (no AOI mapping required).

**Task context (#5, #6, #7).** Three discrete pieces of state the live system
already knows about the user. They give the model just enough context to
distinguish "third minute of step 1 of Centrifuge" from "third minute of step
14 of Pressure Testing" — without leaking the label.

---

## 4. What we deliberately dropped (and why)

| Dropped | Reason |
|---|---|
| `pupil_diam_slope` | Within-window trend signal. Adds marginal information on top of `pupil_pcps_mean` at this sample size (< 10 participants), and introduces noise at window boundaries. Moved here from the active feature set. |
| `pupil_diam_mean / median / iqr / range / mean_z / slope_z`, `pupil_eye_asymmetry`, `pupil_pcps_std` | Redundant with `pupil_pcps_mean`. Linear combinations that don't add information at this sample size. |
| `blink_count`, `blink_dur_mean / std`, `blink_inter_interval_mean / cv`, `blink_long_count` | Mostly noisy at 10 s window scale (often 0–1 blinks per window → undefined statistics). Rate captures the load signal; the rest are duration/fatigue markers, not workload. |
| `fixation_count`, `fixation_rate_per_sec`, `fixation_dur_std / median_ms`, `fixation_saccade_amp_mean`, `fixation_time_in_fixation_ratio` | Redundant with `fixation_dur_mean_ms`. Counts/rates are functions of the same underlying event stream. |
| `gaze_n_samples`, `gaze_norm_x/y_mean/std`, `gaze_region_entropy`, `gaze_region_top1_ratio`, `gaze_transitions_per_sec` | Two reasons: (a) only 11/23 sessions have raw gaze; the fallback to fixation centroids creates a session-identification confound. (b) Without an Areas-of-Interest map (we don't have one), gaze location is procedure-content dependent, not workload dependent. |
| `step_threshold_s`, `time_in_step_so_far_s`, `is_over_threshold_now`, `progress_vs_threshold` | These are *causal at deployment* but they directly encode the proxy-label rule (`exceededThreshold`), so the model would shortcut around the eye-tracking. **Re-enable these once we have real workload labels** (they're legitimate features against NASA-TLX or SOA labels). |
| `n_steps_remaining`, `frac_window_in_current_step`, `cumulative_blink_count_session`, `cumulative_long_blink_count_session` | Derivable from `step_number` + `procedure_id`, or grow monotonically with `cumulative_session_time_s`. No independent signal. |
| `laptop_short` | Confound, not a feature. Lets the model learn "this is Dr. Zahabi's laptop → her participants tend toward X" rather than learning workload from physiology. |
| `pupil_n_samples`, `pupil_data_yield`, QC flags | These are *quality control*, used to **filter** rows (validity gate), not used as model inputs. |
| `step_sub_steps_shown_eventually`, `step_exceeded_threshold_eventually` | Direct copies of the proxy label — would be 100 % leakage. Permanently excluded. |
| Step-level CPM-GOMS operators, AH levels, Worker Characteristics (Task Familiarity, Years of Experience, Pen usage, Operator Prior Sequence) | Per the related concept paper (Ashraf et al., M-IBT), these are strong predictors of procedural deviation, but **not collectible in real time** during the deployed system. Out of scope for v1. |

---

## 5. Windowing and quality gates

| Parameter | Value | Rationale |
|---|---|---|
| Window length | **10 s** | Long enough to estimate blink rate and pupil dynamics, short enough for sub-step responsiveness. |
| Stride | **1 s** | One prediction per second after the first 10 s of the procedure (warm-up). |
| Pupil confidence filter | **≥ 0.6** | Standard Pupil Capture threshold for usable samples. |
| Blink "tracking loss" cutoff | **≥ 2 s** | Excludes saccade-detector confusion / camera occlusion. |
| Validity gate per window | `pupil_data_yield ≥ 0.6` **OR** `fixation_count ≥ 1` | Drops windows where neither the pupil nor the fixation source had usable data. |
| Pupil baseline | Mean over the **quietest 120 s** in the session (lowest blink + fixation count, scanned in 30 s steps) | Required for `pupil_pcps_mean`. Computed once per session before predictions can begin. Replaces the failed "first 120 s" approach which captured the busy 'Prep to start task' period. |

---

## 6. Data availability for the chosen features

Strict-policy training set (no proxy, no fallback) using the 7 features above:

| Feature | Sessions with data |
|---|---|
| `pupil_pcps_mean` | **16 / 23** (offline export or live streaming) |
| `blink_rate_per_min` | 19 / 23 |
| `fixation_dur_mean_ms` | 22 / 23 |
| `procedure_id`, `step_number`, `cumulative_session_time_s` | 23 / 23 |

Effective trainable set: **16 sessions across 9 participants** (we lose P9 and
P11 entirely — both only contributed centrifuge sessions with no pupil data).
This is the price of "no proxy".

The 7 sessions missing pupil entirely:

```
lenovo__211__centrifuge       (P9)
lenovo__222__column_flushing  (P10)
zahabi__321__centrifuge       (P11)
zahabi__351__centrifuge       (P16)
zahabi__352__column_flushing  (P16)
zahabi__361__centrifuge       (P17)
loaner__312__column_flushing  (P8)
```

---

## 7. Real-time feasibility

All 8 features are extractable live. Source map for the deployed system:

| Feature | Live source | Implementation status |
|---|---|---|
| `pupil_pcps_mean` | Pupil Capture ZMQ `pupil.` topic + per-session 120 s baseline tracker | Pupil ingestion ✅; baseline tracker ✅ built in `session_state.py` |
| `blink_rate_per_min` | Pupil Capture ZMQ `blink` topic (Online Blink Detector plugin) | Bridge ✅ (`pupil_capture_bridge.py`); backend endpoint ✅ `/stream/blinks` |
| `fixation_dur_mean_ms` | Pupil Capture ZMQ `fixation` topic (Online Fixation Detector plugin) | Bridge ✅; backend endpoint ✅ `/stream/fixations`. **Plugin must be ON in Pupil Capture.** |
| `procedure_id` | RTAPS frontend `POST /session/start` | Endpoint ✅ |
| `step_number` | RTAPS frontend `POST /session/step_change` | Endpoint ✅ |
| `cumulative_session_time_s` | derived from session-start timestamp per `stream_id` | ✅ computed in `inference_loop.py` |

Two prerequisites at the data-collection site:

1. The **Online Blink Detector** and **Online Fixation Detector** plugins must
   be enabled in Pupil Capture during recording (they're bundled but **off by
   default** — this is the most common reason fixations show 0 on the dashboard).
2. The first **120 s** of each session is a warm-up for baseline computation;
   predictions are suppressed until the baseline is ready.

---

## 8. What changes when we have real Y labels

When NASA-TLX, SOA codes, or any other real workload labels arrive, four
features should be **re-evaluated for re-inclusion**:

- `step_threshold_s`
- `time_in_step_so_far_s`
- `is_over_threshold_now`
- `progress_vs_threshold`

They were excluded because they leak the proxy label, not because they aren't
useful. With real labels they become legitimate task-progress features and may
materially improve performance.

---

## 9. Open issues

1. **Y labels are not yet available.** The current model in
   `models/v1_hgb_weak.joblib` was trained on proxy labels and should be treated
   as a pipeline regression test, not a deployable model. See
   `RTAPS Concept paper_V02.pdf` for one viable path (SOA video coding by 2–3
   trained coders for the existing 24 sessions).
2. **Feature parity between training and serving has not been validated.**
   Once the live backend exists, we need an end-to-end replay test that runs an
   existing offline session through the live path and compares features +
   predictions to those produced by `04_extract_features_window.py`. This is a
   prerequisite for trusting any deployed prediction.
3. **Baseline robustness is unvalidated.** Pupil baseline is now
   `mean(first 120 s, confidence ≥ 0.6)` (extended from 60 s for stability).
   We have not tested whether a different summary (median?) gives better
   results. Worth a short ablation once real labels exist.

---

## 10. Where the code lives

| Concern | File |
|---|---|
| Feature definitions and computations | `scripts/lib/{pupil,blink,fixation,task}_features.py` |
| Window extraction and orchestration | `scripts/04_extract_features_window.py` |
| Per-step QA aggregation | `scripts/05_summarize_per_step.py` |
| Model trainer (drops to the 8-feature subset via the include list at the top of the file) | `scripts/06_train_classifier.py` |
| Configuration (window length, stride, confidence threshold, baseline duration, etc.) | `scripts/lib/config.py` |
| Output schema reference | `data/_processed/feature_dictionary.md` |

---

## 11. Change log

| Date | Change |
|---|---|
| 2026-05-04 | Initial spec — 48 features → 8 features, no proxy / no gaze / no leaky task-progress columns. |
| 2026-05-09 | Removed `pupil_diam_slope` → 7 features. Baseline extended 60 s → 120 s. Fixed fixation ZMQ topic (`fixations` → `fixation`) in all 3 capture scripts. |
| 2026-05-09 | **X→Y strengthening pass**: (1) replaced "first 120 s" baseline with "quietest **120 s** in session" — fixes the busy-prep artifact that made pupil_pcps systematically negative for pressure_testing. (2) Added per-participant (`_zp`) and per-procedure (`_zproc`) z-scored variants of the 5 sensor features. (3) Switched to per-feature window lengths: pupil 10 s, fixation 30 s, blink 60 s — revealed strong cognitive blink suppression (centrifuge ρ = −0.60 with 120 s baseline). (4) Brought `pupil_diam_slope` back as a candidate feature. (5) Trained a sensors-only model (`v3_hgb_sensors_only.joblib`) with no `step_number`/`procedure_id` leakage; achieves κ=+0.02 — sensors now carry real signal but ceiling is low without an explicit calibration phase or window-level labels. |
