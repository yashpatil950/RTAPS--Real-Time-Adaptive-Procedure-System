# RTAPS Streaming Backend

Live ingestion + windowed feature extraction + workload prediction for RTAPS.
There is **no offline path**: the live system reads eye-tracking events from
Pupil Capture and UI events from the RTAPS frontend, and pushes a workload
prediction back out every second. **Nothing is written to CSV on the live
path.**

```
            ┌────────────────┐    ZMQ
            │  Pupil Capture │──pupil/blinks/fixations──┐
            └────────────────┘                          │
                                                        ▼
            ┌─────────────┐  /session/start    ┌─────────────────────────┐
            │ RTAPS UI    │──/step_change ────►│  streaming_backend      │
            └─────────────┘                    │   (this service)        │
                  ▲                            │  per-stream sliding     │
                  │  SSE / GET                 │  10 s window  +  60 s   │
                  │  prediction                │  baseline + every 1 s   │
                  │                            │  → 4 features → model   │
                  └─── /session/{id}/...  ◄────┘
```

## What this service computes

The classifier consumes **4 sensor-only features** (see
`../ML Algorithm/X_FEATURES.md`):

```
pupil_pcps_mean
pupil_diam_slope
blink_rate_30s
fixation_dur_mean_ms
```

`procedure_id`, `step_number`, and `cumulative_session_time_s` are tracked
for UI routing but are **not** model inputs (using them would let the model
read the answer off the step instead of the eyes).

The live extractor in `app/feature_extractor.py` mirrors the training
formulas exactly. The predictor refuses to start if the loaded model's
feature contract does not match `FEATURE_NAMES`.

## API

### Eye-tracking ingress (called by the Pupil Capture bridge)

| method | path | body |
|---|---|---|
| POST | `/stream/pupil` | `{stream_id, samples:[{timestamp, eye_id, diameter, confidence}]}` |
| POST | `/stream/blinks` | `{stream_id, blinks:[{start_timestamp, duration, confidence?}]}` |
| POST | `/stream/fixations` | `{stream_id, fixations:[{start_timestamp, duration, dispersion, norm_x?, norm_y?}]}` |

### UI events (called by the RTAPS frontend)

| method | path | body |
|---|---|---|
| POST | `/session/start` | `{stream_id, procedure_id (1\|2\|3), participant_id?, n_steps_total?}` |
| POST | `/session/step_change` | `{stream_id, step_number, step_id?}` |
| POST | `/session/end` | `{stream_id}` |

### Predictions (read side)

| method | path | what |
|---|---|---|
| GET | `/session/{stream_id}/latest_prediction` | most recent prediction (one-shot) |
| GET | `/session/{stream_id}/predictions/stream` | Server-Sent Events stream, one event per inference tick |
| GET | `/session/{stream_id}/state` | debug snapshot — buffer sizes, baseline status, last prediction |
| GET | `/session/{stream_id}/dashboard` | **RTAPS live UI** — state + pupil series in window + `server_pipeline` metadata |

Browsers hitting the backend from **`http://localhost:3000`** are allowed via CORS (`CORS_ORIGINS` in `.env`; defaults include CRA dev server).

A prediction looks like:

```json
{
  "stream_id": "S001T001",
  "decision_time": 12345.678,
  "procedure_id": 1,
  "step_number": 4,
  "cumulative_session_time_s": 312.4,
  "workload_label": "high",
  "workload_proba": {"low": 0.05, "medium": 0.18, "high": 0.77},
  "feature_values": {
    "pupil_pcps_mean": 0.034,
    "pupil_diam_slope": 0.0042,
    "blink_rate_30s": 3,
    "fixation_dur_mean_ms": 187.3,
    "procedure_id": 1,
    "step_number": 4,
    "cumulative_session_time_s": 312.4
  },
  "inference_source": "local",
  "is_valid_window": true,
  "notes": null
}
```

### Health

| method | path |
|---|---|
| GET | `/health` |
| GET | `/ready` |

## Run locally

Requires Python 3.11+.

```bash
cd streaming_backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # adjust MODEL_PATH if needed
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The default `MODEL_PATH` points at `../ML Algorithm/models/v1_hgb_weak.joblib`,
i.e. the artifact produced by `python "ML Algorithm/scripts/06_train_classifier.py"`.

In a second terminal, start the Pupil Capture bridge (Pupil Capture must be
running with the **Network API**, **Online Blink Detector**, and **Online
Fixation Detector** plugins enabled):

```bash
python pupil_capture_bridge.py --stream_id S001T001
```

In a third terminal, simulate the RTAPS frontend:

```bash
curl -X POST http://127.0.0.1:8000/session/start \
  -H 'content-type: application/json' \
  -d '{"stream_id":"S001T001","procedure_id":1,"participant_id":"P_dev"}'

curl -X POST http://127.0.0.1:8000/session/step_change \
  -H 'content-type: application/json' \
  -d '{"stream_id":"S001T001","step_number":1}'

# Watch predictions live (one event per second once baseline is ready)
curl -N http://127.0.0.1:8000/session/S001T001/predictions/stream
```

## Inference modes

* **Local (default)** — the joblib model is loaded into the backend process
  and predictions are computed in-process. Lowest latency.
* **Remote** — set `FARGATE_INFERENCE_URL` and the backend will POST the
  feature vector (not raw samples) to that URL and use the response. The
  remote service must accept `{stream_id, decision_time, features}` and
  return `{label, proba}`.

## Optional outbound webhook

Set `PREDICTION_WEBHOOK_URL` to have every prediction POSTed to your RTAPS
frontend or any downstream service. Useful when the frontend can't subscribe
to SSE. Errors are logged but never block ingestion.

## Constraints worth knowing

* Predictions are suppressed during the **first 60 s of every session** while
  the per-participant pupil baseline is being collected — the same warm-up
  used at training time.
* A window is marked `is_valid_window=false` (and the `notes` field is
  populated) when the pupil sample yield drops below `MIN_DATA_YIELD` and
  there are no fixations to fall back on. The prediction is still emitted —
  it's the consumer's choice whether to act on it.
* All eye-tracking events MUST share a clock (Pupil Capture's
  `pupil_timestamp`). The bridge ensures this; no clock conversion is asked
  of the frontend, which only needs to call `/session/start` and
  `/session/step_change` at the right moments.
