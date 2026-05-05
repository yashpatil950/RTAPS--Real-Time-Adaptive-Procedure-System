"""Asynchronous inference tick.

Once per `STRIDE_S` seconds we walk every active session, compute the 8
features over its current window, run the prediction (locally or remote),
publish the result on the per-session SSE channel, and optionally POST it
to the configured frontend webhook.

Runs as a single background asyncio task started from the FastAPI lifespan
(see `main.py`). One loop, no per-session timers — that keeps the cost
constant in number of streams and sidesteps drift between independent timers.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from app.config import settings
from app.fargate_client import predict_remote, push_prediction_webhook
from app.feature_extractor import extract_features
from app.predictor import LocalPredictor
from app.session_state import SessionRegistry, SessionState

log = logging.getLogger(__name__)


class InferenceLoop:
    def __init__(
        self,
        registry: SessionRegistry,
        predictor: Optional[LocalPredictor],
    ):
        self._registry = registry
        self._predictor = predictor
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._sse_queues: dict[str, list[asyncio.Queue]] = {}

    # ---- lifecycle ------------------------------------------------------ #

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="inference-loop")
            log.info("Inference loop started (stride=%.2fs)", settings.stride_s)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None
        log.info("Inference loop stopped")

    # ---- SSE plumbing --------------------------------------------------- #

    def subscribe(self, stream_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._sse_queues.setdefault(stream_id, []).append(q)
        return q

    def unsubscribe(self, stream_id: str, q: asyncio.Queue) -> None:
        if stream_id in self._sse_queues:
            try:
                self._sse_queues[stream_id].remove(q)
            except ValueError:
                pass
            if not self._sse_queues[stream_id]:
                self._sse_queues.pop(stream_id, None)

    def _publish_sse(self, stream_id: str, prediction: dict) -> None:
        for q in list(self._sse_queues.get(stream_id, [])):
            if q.full():
                try:
                    q.get_nowait()  # drop oldest, keep newest
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(prediction)
            except asyncio.QueueFull:
                pass

    # ---- main loop ------------------------------------------------------ #

    async def _run(self) -> None:
        try:
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    await self._tick_once()
                except Exception as exc:
                    log.exception("Inference tick crashed: %s", exc)

                elapsed = time.monotonic() - started
                await asyncio.sleep(max(0.0, settings.stride_s - elapsed))
        except asyncio.CancelledError:
            pass

    async def _tick_once(self) -> None:
        sessions = self._registry.all()
        if not sessions:
            await self._registry.evict_idle()
            return
        for st in sessions:
            try:
                await self._maybe_predict(st)
            except Exception as exc:
                log.exception("Predicting for stream %s failed: %s", st.stream_id, exc)
        await self._registry.evict_idle()

    async def _maybe_predict(self, st: SessionState) -> None:
        async with st.lock:
            st.maybe_anchor_session_start()
            if not st.is_ready_for_inference():
                return

            assert st.latest_pupil_t is not None
            assert st.session_started_at is not None
            assert st.procedure_id is not None
            assert st.step_number is not None

            decision_t = st.latest_pupil_t
            cumulative = decision_t - st.session_started_at
            arrays = st.window_arrays()
            baseline = st.baseline.baseline()

            features, is_valid, qa = extract_features(
                pupil_t=arrays["pupil_t"],
                pupil_eye=arrays["pupil_eye"],
                pupil_diam_mm=arrays["pupil_diam"],
                blink_durations_s=arrays["blink_durations_s"],
                fix_durations_s=arrays["fix_durations_s"],
                fix_dispersion=arrays["fix_dispersion"],
                baseline=baseline,
                procedure_id=st.procedure_id,
                step_number=st.step_number,
                cumulative_session_time_s=cumulative,
                window_len_s=settings.window_len_s,
                expected_pupil_rate_hz_per_eye=settings.expected_pupil_rate_hz_per_eye,
                min_data_yield=settings.min_data_yield,
            )

            if settings.fargate_inference_url:
                label, proba = await predict_remote(st.stream_id, decision_t, features)
                source = "remote"
            else:
                if self._predictor is None:
                    log.warning("No local predictor and no FARGATE_INFERENCE_URL set; skipping.")
                    return
                label, proba = self._predictor.predict(features)
                source = "local"

            prediction: dict = {
                "stream_id": st.stream_id,
                "decision_time": decision_t,
                "procedure_id": int(st.procedure_id),
                "step_number": int(st.step_number),
                "cumulative_session_time_s": float(cumulative),
                "workload_label": label,
                "workload_proba": proba,
                "feature_values": features,
                "inference_source": source,
                "is_valid_window": bool(is_valid),
                "notes": None if is_valid else "low data yield in window — prediction may be unreliable",
                "qa": qa,
            }
            st.last_prediction = prediction
            st.latest_prediction_at_wall = time.time()

        # Publish outside the per-session lock so slow consumers don't block ingress.
        self._publish_sse(st.stream_id, prediction)
        await push_prediction_webhook(prediction)
