"""FastAPI app for the RTAPS live streaming backend.

Endpoints
---------

Eye-tracking ingress (Pupil Capture bridge):
    POST /stream/pupil          batch of PupilSample
    POST /stream/blinks         batch of BlinkEvent
    POST /stream/fixations      batch of FixationEvent

UI events (RTAPS frontend):
    POST /session/start         registers a new session (procedure_id, etc.)
    POST /session/step_change   updates current step number
    POST /session/end           drops the session's in-memory state

Predictions (read side):
    GET  /session/{stream_id}/latest_prediction          one-shot pull
    GET  /session/{stream_id}/predictions/stream         SSE push channel
    GET  /session/{stream_id}/state                      debug snapshot

Health:
    GET /health
    GET /ready

Nothing is persisted to disk on the live path. Every prediction is
computed from the current 10 s window and pushed to the UI immediately.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse


from app.config import settings
from app.inference_loop import InferenceLoop
from app.predictor import LocalPredictor
from app.schemas import (
    BlinkIngestRequest,
    CalibrationEndRequest,
    CalibrationStartRequest,
    FixationIngestRequest,
    HealthResponse,
    IngestResponse,
    PredictionResponse,
    PupilIngestRequest,
    RawIngestRequest,
    SessionAck,
    SessionEndRequest,
    SessionStartRequest,
    SessionStateView,
    StepChangeRequest,
)
from app.session_state import BlinkRec, FixRec, PupilRec, SessionRegistry
from app import raw_store

log = logging.getLogger("rtaps.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# --------------------------------------------------------------------------- #
# Lifespan: initialize registry + predictor + inference loop                  #
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI):
    registry = SessionRegistry(
        window_len_s=settings.window_len_s,
        fixation_window_len_s=settings.fixation_window_len_s,
        blink_window_len_s=settings.blink_window_len_s,
        baseline_duration_s=settings.baseline_duration_s,
        min_confidence=settings.min_confidence,
        blink_tracking_loss_s=settings.blink_tracking_loss_s,
        idle_ttl_s=settings.session_idle_ttl_s,
        record_raw=settings.raw_data_enabled,
        raw_max_samples=settings.raw_data_max_samples,
    )

    predictor: LocalPredictor | None = None
    if not settings.fargate_inference_url:
        predictor = LocalPredictor(settings.model_path)
        try:
            predictor.load()
        except Exception as exc:
            log.error("Failed to load local model: %s", exc)
            log.error(
                "Set FARGATE_INFERENCE_URL to use remote inference, or fix MODEL_PATH (currently %s).",
                settings.model_path,
            )
            raise

    loop = InferenceLoop(registry, predictor)
    loop.start()

    app.state.registry = registry
    app.state.predictor = predictor
    app.state.loop = loop
    try:
        yield
    finally:
        await loop.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Health                                                                      #
# --------------------------------------------------------------------------- #


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    return HealthResponse(
        status="ready",
        extras={
            "inference_mode": "remote" if settings.fargate_inference_url else "local",
            "model_path": str(settings.model_path) if not settings.fargate_inference_url else None,
            "window_len_s": settings.window_len_s,
            "stride_s": settings.stride_s,
            "baseline_duration_s": settings.baseline_duration_s,
            "min_confidence": settings.min_confidence,
            "active_streams": len(app.state.registry.all()),
        },
    )


# --------------------------------------------------------------------------- #
# Eye-tracking ingress                                                        #
# --------------------------------------------------------------------------- #


def _ingest_response(st) -> IngestResponse:
    view = st.view()
    return IngestResponse(
        stream_id=st.stream_id,
        accepted=0,
        pupil_samples_buffered=view["pupil_samples_buffered"],
        blinks_buffered=view["blinks_buffered"],
        fixations_buffered=view["fixations_buffered"],
        baseline_ready=view["baseline_ready"],
        seconds_until_first_prediction=st.seconds_until_first_prediction(),
    )


@app.post("/stream/pupil", response_model=IngestResponse)
async def ingest_pupil(req: PupilIngestRequest) -> IngestResponse:
    st = await app.state.registry.get_or_create(req.stream_id)
    recs = [
        PupilRec(t=s.timestamp, eye_id=s.eye_id, diameter=s.diameter, confidence=s.confidence)
        for s in req.samples
    ]
    async with st.lock:
        accepted = st.add_pupil(recs)
        st.maybe_anchor_session_start()
    resp = _ingest_response(st)
    resp.accepted = accepted
    return resp


@app.post("/stream/blinks", response_model=IngestResponse)
async def ingest_blinks(req: BlinkIngestRequest) -> IngestResponse:
    st = await app.state.registry.get_or_create(req.stream_id)
    recs = [
        BlinkRec(t=b.start_timestamp, duration=b.duration, tracking_loss=False)
        for b in req.blinks
    ]
    async with st.lock:
        accepted = st.add_blinks(recs)
    resp = _ingest_response(st)
    resp.accepted = accepted
    return resp


@app.post("/stream/fixations", response_model=IngestResponse)
async def ingest_fixations(req: FixationIngestRequest) -> IngestResponse:
    st = await app.state.registry.get_or_create(req.stream_id)
    recs = [
        FixRec(t=f.start_timestamp, duration=f.duration, dispersion=f.dispersion)
        for f in req.fixations
    ]
    async with st.lock:
        accepted = st.add_fixations(recs)
    resp = _ingest_response(st)
    resp.accepted = accepted
    return resp


@app.post("/stream/raw", response_model=IngestResponse)
async def ingest_raw(req: RawIngestRequest) -> IngestResponse:
    """Unfiltered raw archival channel — full Pupil payloads stored verbatim,
    independent of the feature pipeline (see SessionState.add_raw_events)."""
    st = await app.state.registry.get_or_create(req.stream_id)
    async with st.lock:
        accepted = st.add_raw_events(pupil=req.pupil, blinks=req.blinks, fixations=req.fixations)
    resp = _ingest_response(st)
    resp.accepted = accepted
    return resp


# --------------------------------------------------------------------------- #
# UI events                                                                   #
# --------------------------------------------------------------------------- #


@app.post("/session/start", response_model=SessionAck)
async def session_start(req: SessionStartRequest) -> SessionAck:
    st = await app.state.registry.get_or_create(req.stream_id)
    async with st.lock:
        st.mark_session_start(
            procedure_id=req.procedure_id,
            participant_id=req.participant_id,
            n_steps_total=req.n_steps_total,
            mode=req.mode,
        )
    return SessionAck(
        stream_id=req.stream_id,
        status="started",
        message=(
            f"Procedure {req.procedure_id} registered. "
            f"Predictions will start once {settings.window_len_s:.0f}s of data and the "
            f"{settings.baseline_duration_s:.0f}s baseline are collected."
        ),
    )


@app.post("/session/calibration_start", response_model=SessionAck)
async def session_calibration_start(req: CalibrationStartRequest) -> SessionAck:
    """Operator is sitting calmly at the fixation cross. Begin baseline
    accumulation. Predictions remain suppressed until calibration_end."""
    st = await app.state.registry.get_or_create(req.stream_id)
    async with st.lock:
        st.mark_calibration_start()
    return SessionAck(
        stream_id=req.stream_id,
        status="calibration_started",
        message=(
            f"Calibration in progress. Pupil samples are being accumulated. "
            f"Target duration: {settings.baseline_duration_s:.0f}s. "
            f"POST /session/calibration_end when the calibration screen completes."
        ),
    )


@app.post("/session/calibration_end", response_model=SessionAck)
async def session_calibration_end(req: CalibrationEndRequest) -> SessionAck:
    """Freeze the baseline using whatever samples were collected during
    calibration. After this, the procedure may begin and predictions are
    enabled from step 1 second 0."""
    st = app.state.registry.get(req.stream_id)
    if st is None:
        raise HTTPException(404, f"No active session for stream_id={req.stream_id}")
    async with st.lock:
        ok = st.mark_calibration_end()
        view = st.view()
        # Pull live diagnostic state from the tracker — this is *much* more
        # accurate than guessing from pupil_received_total alone.
        acc0, acc1 = st.baseline.accumulator_counts()
        explicit_active = st.baseline.explicit_active()
    if not ok:
        pupil_total = view.get("pupil_received_total", 0)
        all_streams = [s.stream_id for s in app.state.registry.all()]
        other_active = [sid for sid in all_streams if sid != req.stream_id]
        hint_lines = [
            "Calibration ended but no usable pupil samples were collected.",
            f"Diagnostics for stream_id={req.stream_id!r}:",
            f"  pupil_received_total = {pupil_total}",
            f"  baseline_accumulator = eye0:{acc0}  eye1:{acc1}",
            f"  explicit_calibration_mode = {explicit_active}",
        ]
        if pupil_total == 0:
            hint_lines.append(
                "  → No pupil samples ever reached THIS session_id."
            )
            if other_active:
                hint_lines.append(
                    "  → Other active stream_ids on this backend: "
                    + ", ".join(repr(s) for s in other_active)
                    + ". The Pupil Capture bridge is likely running with a "
                    "different --stream_id than the frontend is using. "
                    "Restart the bridge with --stream_id matching the value "
                    "shown in the frontend's streaming banner (or set "
                    "localStorage.rtaps_pupil_stream_id before starting the "
                    "session)."
                )
            else:
                hint_lines.append(
                    "  → No bridge is forwarding to the backend at all. "
                    "Start `python pupil_capture_bridge.py --stream_id "
                    f"{req.stream_id}` and try again."
                )
        elif not explicit_active:
            hint_lines.append(
                "  → calibration_start was never recorded for this session. "
                "The frontend's calibration screen may not have called "
                "/session/calibration_start before /session/calibration_end. "
                "Try restarting the calibration."
            )
        elif acc0 == 0 and acc1 == 0:
            hint_lines.append(
                "  → calibration_start fired but ZERO pupil samples landed "
                "in the baseline accumulator. The bridge probably stopped "
                "forwarding samples between calibration_start and "
                "calibration_end (check the bridge terminal). Or every "
                "sample in that window failed the confidence filter — open "
                "Pupil Capture and verify both eye windows are tracking "
                "(green ellipses) before restarting calibration."
            )
        else:
            hint_lines.append(
                "  → Internal error: accumulators non-empty but finalize "
                "still failed. Please report this."
            )
        return SessionAck(
            stream_id=req.stream_id,
            status="calibration_insufficient_samples",
            message="\n".join(hint_lines),
        )
    return SessionAck(
        stream_id=req.stream_id,
        status="calibration_completed",
        message="Baseline frozen. Procedure may now begin — predictions enabled from step 1.",
    )


@app.post("/session/step_change", response_model=SessionAck)
async def session_step_change(req: StepChangeRequest) -> SessionAck:
    st = app.state.registry.get(req.stream_id)
    if st is None:
        raise HTTPException(404, f"No active session for stream_id={req.stream_id}")
    async with st.lock:
        st.mark_step_change(req.step_number, req.step_id)
    return SessionAck(
        stream_id=req.stream_id,
        status="step_updated",
        message=f"step_number={req.step_number}",
    )


@app.post("/session/end", response_model=SessionAck)
async def session_end(req: SessionEndRequest) -> SessionAck:
    st = app.state.registry.get(req.stream_id)
    archived_key: str | None = None
    if st is not None and settings.raw_data_enabled and st.has_raw():
        # Build the raw document under the session lock, then write it off the
        # event loop (boto3/disk I/O is blocking).
        async with st.lock:
            dataset = st.raw_dataset(extra_meta={"ended_at": time.time()})
        try:
            index = await asyncio.to_thread(raw_store.persist_session, dataset)
            archived_key = index.get("key")
        except Exception as exc:  # noqa: BLE001 - never fail the UI on archival error
            log.error("raw archival failed for %s: %s", req.stream_id, exc)
    dropped = await app.state.registry.drop(req.stream_id)
    return SessionAck(
        stream_id=req.stream_id,
        status="ended" if dropped else "not_found",
        message=(f"Raw session archived: {archived_key}" if archived_key else None),
    )


# --------------------------------------------------------------------------- #
# Raw eye-data archive                                                         #
# --------------------------------------------------------------------------- #


@app.get("/raw_sessions")
async def list_raw_sessions() -> dict:
    """Index of archived raw sessions (metadata only)."""
    try:
        sessions = await asyncio.to_thread(raw_store.list_sessions)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Could not list raw sessions: {exc}") from exc
    return {
        "storage": "s3" if raw_store.use_s3() else "local",
        "bucket": settings.raw_data_s3_bucket or None,
        "count": len(sessions),
        "sessions": sessions,
    }


@app.get("/raw_sessions/{key:path}/download")
async def download_raw_session(key: str):
    """Download one raw file: redirect to a presigned S3 URL, or stream the
    local file when archival is on disk."""
    if raw_store.use_s3():
        url = await asyncio.to_thread(raw_store.presign_url, key)
        if not url:
            raise HTTPException(404, "Raw session not found")
        return RedirectResponse(url)
    path = raw_store.local_path(key)
    if path is None:
        raise HTTPException(404, "Raw session not found")
    return FileResponse(path, media_type="application/gzip", filename=path.name)


@app.delete("/raw_sessions/{key:path}", response_model=SessionAck)
async def delete_raw_session(key: str) -> SessionAck:
    try:
        removed = await asyncio.to_thread(raw_store.delete_session, key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Could not delete raw session: {exc}") from exc
    return SessionAck(stream_id=key, status="deleted" if removed else "not_found")


# --------------------------------------------------------------------------- #
# Predictions / debug                                                         #
# --------------------------------------------------------------------------- #


@app.get("/session/{stream_id}/latest_prediction", response_model=PredictionResponse)
async def latest_prediction(stream_id: str) -> PredictionResponse:
    st = app.state.registry.get(stream_id)
    if st is None or st.last_prediction is None:
        raise HTTPException(404, f"No prediction yet for stream_id={stream_id}")
    return PredictionResponse(**{k: v for k, v in st.last_prediction.items() if k != "qa"})


@app.get("/session/{stream_id}/predictions/stream")
async def stream_predictions(stream_id: str, request: Request):
    """Server-Sent Events stream of predictions for one session."""
    loop: InferenceLoop = app.state.loop
    queue = loop.subscribe(stream_id)

    async def event_gen():
        try:
            # Send the latest prediction immediately if we have one.
            st = app.state.registry.get(stream_id)
            if st is not None and st.last_prediction is not None:
                yield f"data: {json.dumps({k: v for k, v in st.last_prediction.items() if k != 'qa'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    pred = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps({k: v for k, v in pred.items() if k != 'qa'})}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            loop.unsubscribe(stream_id, queue)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/session/{stream_id}/dashboard")
async def session_dashboard(stream_id: str) -> dict:
    """Combined eye-tracker preview + sliding-window metadata for the RTAPS UI."""
    st = app.state.registry.get(stream_id)
    if st is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active session for stream_id={stream_id}. "
            "Forward pupil data once or POST /session/start with this id.",
        )
    async with st.lock:
        snap = st.dashboard_snapshot()
    snap["server_pipeline"] = {
        "window_len_s": settings.window_len_s,
        "stride_s": settings.stride_s,
        "baseline_duration_s": settings.baseline_duration_s,
        "expected_pupil_rate_hz_per_eye": settings.expected_pupil_rate_hz_per_eye,
        "min_confidence": settings.min_confidence,
        "min_data_yield": settings.min_data_yield,
    }
    return snap


@app.get("/session/{stream_id}/state", response_model=SessionStateView)
async def session_state(stream_id: str) -> SessionStateView:
    st = app.state.registry.get(stream_id)
    if st is None:
        raise HTTPException(404, f"No active session for stream_id={stream_id}")
    view = st.view()
    last_pred = view.get("last_prediction")
    if last_pred is not None:
        last_pred = PredictionResponse(**{k: v for k, v in last_pred.items() if k != "qa"})
    return SessionStateView(
        stream_id=view["stream_id"],
        procedure_id=view["procedure_id"],
        step_number=view["step_number"],
        participant_id=view["participant_id"],
        session_started_at=view["session_started_at"],
        calibration_started_at=view.get("calibration_started_at"),
        calibration_ended_at=view.get("calibration_ended_at"),
        calibrating=bool(view.get("calibrating", False)),
        baseline_mode=view.get("baseline_mode", "") or "",
        baseline_seconds_remaining=view.get("baseline_seconds_remaining"),
        latest_pupil_t=view["latest_pupil_t"],
        latest_prediction_at=view["latest_prediction_at"],
        pupil_samples_buffered=view["pupil_samples_buffered"],
        blinks_buffered=view["blinks_buffered"],
        fixations_buffered=view["fixations_buffered"],
        pupil_received_total=view.get("pupil_received_total", 0),
        blinks_received_total=view.get("blinks_received_total", 0),
        fixations_received_total=view.get("fixations_received_total", 0),
        last_blink_received_at=view.get("last_blink_received_at"),
        last_fixation_received_at=view.get("last_fixation_received_at"),
        baseline_ready=view["baseline_ready"],
        baseline=view["baseline"],
        last_prediction=last_pred,
    )
