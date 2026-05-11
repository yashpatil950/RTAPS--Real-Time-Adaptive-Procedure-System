# Running the full RTAPS system

End-to-end pipeline:

```
Pupil Capture (eye tracker)
        │  ZMQ
        ▼
pupil_capture_bridge.py  ────HTTP POST batches───▶  Streaming_Backend (FastAPI :8000)
                                                            │
                                                            │  SSE  /session/<id>/predictions/stream
                                                            ▼
                                                    RTAPS_Frontend (React :3000)
                                                    ↳ SessionView shows live workload-based
                                                      instructions, cumulative as level escalates
```

## 1. Start the streaming backend

```bash
cd Streaming_Backend
pip install -r requirements.txt   # first time only
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

You should see:

```
INFO  app.predictor: Loaded model .../v2_hgb_vacp.joblib (7 features, classes=['low','medium','high'])
INFO  app.inference_loop: Inference loop started (stride=1.00s)
INFO  Uvicorn running on http://127.0.0.1:8000
```

Verify:

```bash
curl http://127.0.0.1:8000/health   # → {"status":"ok"}
curl http://127.0.0.1:8000/ready    # shows model path, window/baseline settings
```

## 2. Start the frontend

```bash
cd RTAPS_Frontend
npm install                           # first time only
REACT_APP_STREAMING_API_URL=http://127.0.0.1:8000 npm start
```

Open `http://localhost:3000`, log in, pick a procedure, and start a session.
The blue "Streaming ML: …" banner at the top of the SessionView should turn
into "Streaming ML: live  [LOW]" once the first prediction arrives.

## 3. Connect the eye tracker

On the laptop running Pupil Capture, open Pupil Capture and **enable**:

- **Network API** plugin (default port 50020)
- **Online Blink Detector** plugin
- **Online Fixation Detector** plugin (this is required — without it, fixation features are zero and predictions degrade)

Then run the bridge in a third terminal:

```bash
cd Streaming_Backend
python pupil_capture_bridge.py --stream_id <SAME_ID_AS_FRONTEND>
```

The frontend's stream ID is shown in the streaming banner. By default it's
auto-derived from `RTAPS_<participant>_P<procedure>_T<train>` — you can also
set it manually via `localStorage.rtaps_pupil_stream_id`.

## 4. What you'll see in the UI

For each step in the procedure:

| Workload state | What appears |
|---|---|
| `low` (initial) | No additional guidance — only the base step description |
| `medium` (model predicts medium) | Yellow "Additional Guidance" block with key bullet points |
| `high` (model escalates to high) | Yellow medium block **stays visible**, plus an orange "Detailed Explanation" block with Why / What / How |
| Drops back from high → medium | Both blocks remain (display level is sticky to highest reached) |

**Cumulative display** is the key behavior the user requested: once the
model has shown medium for a step, it never disappears even if the level
later goes higher.

The 30-second `WorkloadSmoother` prevents jittery instruction changes —
the on-screen level only updates when the model's new label has held for
30 consecutive seconds, and direction-guarded (e.g., `low → high` must
pass through `medium` first).

## 5. Without the eye tracker (UI-only test)

The frontend has a time-threshold fallback. If no streaming predictions
arrive (e.g., bridge not running, baseline still warming up):

- Past the step's `timeThreshold` → escalates to `medium`
- Past 1.5× threshold → escalates to `high`

Toggle dev mode in the SessionView to override the level manually with
the Low/Medium/High buttons.

## 6. Architecture quick-ref

| Component | Path |
|---|---|
| FastAPI app | `Streaming_Backend/app/main.py` |
| Per-session state + baseline tracker | `Streaming_Backend/app/session_state.py` |
| Inference loop (1 s tick) | `Streaming_Backend/app/inference_loop.py` |
| Workload smoother (30 s gate + direction guard) | `Streaming_Backend/app/workload_smoother.py` |
| Local model wrapper | `Streaming_Backend/app/predictor.py` |
| Pupil Capture bridge | `Streaming_Backend/pupil_capture_bridge.py` |
| Frontend session page (the live UI) | `RTAPS_Frontend/src/pages/SessionView.js` |
| Frontend streaming API client | `RTAPS_Frontend/src/services/streamingApi.js` |
| Per-step instructions (medium/high feedback) | `RTAPS_Frontend/src/data/stepFeedback.js` |
| ML model artifact | `ML Algorithm/models/v2_hgb_vacp.joblib` |

## 7. Troubleshooting

**No predictions appearing:** check `/ready` to confirm the model loaded,
then `/session/<id>/state` to see if pupil samples are buffered and the
baseline is finalized (takes 120 s of pupil data). If `baseline_ready`
is `false` after 2 minutes, no pupil samples are reaching the backend —
verify the bridge is running and posting to the right `/stream/pupil`
endpoint.

**Predictions arrive but UI shows nothing:** check the streaming banner
shows the matching `stream_id`. The frontend filters predictions by
`step_number` — if the frontend's current step doesn't match the
backend's, nothing renders. Click through a step to trigger a
`step_change` POST.

**500 errors on `/session/{id}/state`:** if a sensor stream is empty
(no fixations, etc.) the model produces NaN feature values which used
to break JSON serialization. Already fixed in `inference_loop.py`
(`_json_safe`); restart the backend if you hit this on an old build.
