# RTAPS Live Workload System — Presentation Overview

Short briefing document: how the live pipeline works, how to run it, inputs (**X**), labels (**Y**) status, streaming architecture, outputs, and UX-oriented improvements.

---

## 1. Goal

Estimate **cognitive workload** (**low / medium / high**) **in real time** while an operator runs an RTAPS procedure, using **eye tracking** (pupil, blinks, fixations) plus **minimal task context** from the UI. Downstream use: **adaptive guidance** when the worker is overloaded or stuck—not necessarily flashing new text every second.

---

## 2. How it works (conceptually)

1. **Pupil Capture** detects eyes and publishes **pupil samples**, **blinks**, and **fixations** over an internal **ZMQ** bus (Network API).
2. **`pupil_capture_bridge.py`** subscribes to that bus and **forwards** events to the **streaming backend** via **HTTP** (`POST /stream/pupil`, `/stream/blinks`, `/stream/fixations`). All use one **`stream_id`** per session.
3. The **RTAPS frontend** (or `curl` during dev) tells the backend **which procedure** and **which step** (`POST /session/start`, `/session/step_change`).
4. The backend keeps a **rolling buffer** of eye data (~**10 s** feature window), builds a **personal pupil baseline** over the first ~**60 s**, then about **once per second** computes **8 features** and runs the **ML model**.
5. **Output**: workload **label**, **class probabilities**, **feature snapshot**, validity flags—exposed over **HTTP** and **SSE** for dashboards or policies.

**Canonical detail:** `Streaming_Backend/README.md`, `ML Algorithm/X_FEATURES.md`.

---

## 3. Streaming architecture (data flow)

```
┌─────────────────┐     ZMQ      ┌──────────────────────┐     HTTP      ┌─────────────────────────┐
│ Pupil Capture   │ ───────────► │ pupil_capture_bridge │ ────────────► │ streaming_backend       │
│ (+ detectors)   │              │ (same PC as Pupil)   │  /stream/*    │ rolling buffers + model │
└─────────────────┘              └──────────────────────┘               └────────────┬────────────┘
                                                                                     │
┌─────────────────┐     HTTP                         ┌──────────────────────────────┴──────────────┐
│ RTAPS UI / curl │ ───── /session/start, ─────────► │ Inference ~1 Hz · 10 s window · 60 s baseline │
│                 │      /session/step_change        └───────────────────────────────────────────────┘
└─────────────────┘                                                    │
                                                                       ▼
                                                          predictions (HTTP / SSE / optional webhook)
```

**Windows (defaults):**

| Idea | Duration | Role |
|------|----------|------|
| **Feature window** | ~10 s (`WINDOW_LEN_S`) | Only recent physiology is summarized—matches how the model was trained. |
| **Baseline** | ~60 s (`BASELINE_DURATION_S`) | First-minute pupil used for **normalization** (% change vs self)—not the same as the 10 s window. |
| **Inference stride** | ~1 s (`STRIDE_S`) | How often a **new prediction** is emitted internally. |

---

## 4. Setup (local demo)

**Prerequisites:** Python **3.11+**, Pupil Capture with **Network API**, **Blink Detector**, **Fixation Detector** enabled; same `stream_id` everywhere.

**A. Backend** (from repo root, adjust path if needed):

```powershell
cd Streaming_Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**B. Bridge** (machine running Pupil):

```powershell
cd Streaming_Backend
python pupil_capture_bridge.py --stream_id YOUR_STREAM_ID --backend_url http://127.0.0.1:8000
```

Optional: `--verbose` to debug fixation/ZMQ topics.

**C. Session + step** (simulate UI):

```bash
curl -X POST http://127.0.0.1:8000/session/start -H "content-type: application/json" -d "{\"stream_id\":\"YOUR_STREAM_ID\",\"procedure_id\":1,\"participant_id\":\"P_demo\"}"
curl -X POST http://127.0.0.1:8000/session/step_change -H "content-type: application/json" -d "{\"stream_id\":\"YOUR_STREAM_ID\",\"step_number\":1}"
```

**D. Watch predictions:**

```bash
curl -N http://127.0.0.1:8000/session/YOUR_STREAM_ID/predictions/stream
```

**Frontend:** Streaming dashboard uses the same backend URL and `stream_id`. Full API tables: `Streaming_Backend/README.md`.

---

## 5. Inputs: the 8 **X** features (what they mean, short)

The model uses **eight** inputs only. Full spec and rationale: **`ML Algorithm/X_FEATURES.md`**.

| # | Feature | Short meaning |
|---|---------|----------------|
| 1 | `pupil_pcps_mean` | Pupil size vs **this person’s** ~60 s baseline (% change)—classic load signal. |
| 2 | `pupil_diam_slope` | Trend of pupil diameter over the **last ~10 s** (rising vs falling). |
| 3 | `blink_rate_per_min` | Blinks per minute (tracking-loss blinks excluded). |
| 4 | `fixation_dur_mean_ms` | Average fixation **duration** in the window (ms). |
| 5 | `fixation_dispersion_mean` | Average fixation **spatial spread / jitter** (stability proxy). |
| 6 | `procedure_id` | Which procedure (1–3). |
| 7 | `step_number` | Current step index. |
| 8 | `cumulative_session_time_s` | Seconds since session start (fatigue / drift). |

---

## 6. Labels: **Y** (status)

- **Target:** workload class **low / medium / high** (per decision time / window).
- **Current status:** **`Y` is still pending.** `X_FEATURES.md` states the **X** side is finalized; **trustworthy training labels** (e.g. NASA-TLX, observer ratings, structured SOA—not procedural proxy rules) are **still needed** before treating production models as validated.
- Until then: existing joblib artifacts may use **weak/proxy** labels—fine for **pipeline demos**, not for strong scientific or regulatory claims.

---

## 7. Output (what you get each inference tick)

Roughly each **second** (once baseline + window readiness conditions are met), the API returns JSON including:

- **`workload_label`** — `low` | `medium` | `high`
- **`workload_proba`** — class probabilities
- **`feature_values`** — the 8 **X** numbers used
- **`is_valid_window`** — whether data quality met gates (consumer may ignore low-quality ticks)
- **`procedure_id`**, **`step_number`**, **`cumulative_session_time_s`**, timestamps, optional **`notes`**

Example shape: `Streaming_Backend/README.md` (prediction JSON).

---

## 8. Why predictions change often — and improvements for workers

**Why it jitters:** physiology varies continuously; the model reads a **moving 10 s slice** and outputs probabilities—small shifts can flip the **argmax** label.

**Risk:** If **worker-facing instructions** mirror raw API output **every second**, guidance can feel chaotic.

**Recommended improvements (policy layer — does not require changing the ML core):**

1. **Minimum dwell:** only change displayed guidance if the new band holds for **N seconds** or **M consecutive** ticks (e.g. 5–15 s).
2. **Hysteresis:** different thresholds for moving **up** to “high” vs **down** to “medium/low”.
3. **Smoothing:** exponential moving average or rolling mean on a score or on **high** probability before thresholding.
4. **Edge-triggered UI:** show **one** intervention when crossing into sustained high, not on every bounce.
5. **Combine with task rules:** e.g. adapt only if **step time exceeds threshold** *and* workload is high—aligns with RTAPS step logic.

**Design principle:** Keep **fast inference** for monitoring/logging; use a **slower, stable policy** for **instructions** (`X_FEATURES.md` §1 already assumes a downstream aggregator for UI).

---

## 9. File pointers

| Topic | Location |
|-------|----------|
| Live API & run commands | `Streaming_Backend/README.md` |
| Feature contract (**X**) | `ML Algorithm/X_FEATURES.md` |
| Bridge (ZMQ → HTTP) | `Streaming_Backend/pupil_capture_bridge.py` |
| Window / baseline / stride defaults | `Streaming_Backend/app/config.py` |

---

*Document for internal presentation; align numbers with `.env` / `config.py` if overridden.*
