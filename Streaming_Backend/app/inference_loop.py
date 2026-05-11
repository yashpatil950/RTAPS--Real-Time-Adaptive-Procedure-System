"""Asynchronous inference tick.

Once per `STRIDE_S` seconds we walk every active session, compute the 7
features over its current window, run the prediction (locally or remote),
pass the raw label through a WorkloadSmoother (30-second stability gate +
direction guard), publish the stable result on the per-session SSE channel,
and optionally POST it to the configured frontend webhook.

Runs as a single background asyncio task started from the FastAPI lifespan
(see `main.py`). One loop, no per-session timers — that keeps the cost
constant in number of streams and sidesteps drift between independent timers.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Optional

from app.config import settings
from app.fargate_client import predict_remote, push_prediction_webhook
from app.feature_extractor import extract_features
from app.predictor import LocalPredictor
from app.session_state import SessionRegistry, SessionState
from app.workload_smoother import WorkloadSmoother


def _json_safe(d: dict) -> dict:
    """Convert NaN / inf floats to None so the dict is valid JSON.

    Stdlib `json.dumps` with `allow_nan=False` (FastAPI's default) and
    `pydantic v2` both reject NaN. The model produces NaN for sensor
    features when their source had no data in the window (e.g. zero blinks
    in 60 s) — the trained HGB classifier handles NaN natively, but the
    response payload must be JSON-compliant.
    """
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, float) and not math.isfinite(v):
            out[k] = None
        else:
            out[k] = v
    return out

log = logging.getLogger(__name__)


class InferenceLoop:
    def __init__(
        self,
        registry: SessionRegistry,
        predictor: Optional[LocalPredictor],
        smoother_stability_s: int = 30,
    ):
        self._registry = registry
        self._predictor = predictor
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._sse_queues: dict[str, list[asyncio.Queue]] = {}
        # One WorkloadSmoother per active stream; created lazily.
        self._smoothers: dict[str, WorkloadSmoother] = {}
        self._smoother_stability_s = smoother_stability_s

    def _get_smoother(self, stream_id: str) -> WorkloadSmoother:
        if stream_id not in self._smoothers:
            self._smoothers[stream_id] = WorkloadSmoother(self._smoother_stability_s)
        return self._smoothers[stream_id]

    def drop_smoother(self, stream_id: str) -> None:
        """Call when a session ends so the smoother's memory is freed."""
        self._smoothers.pop(stream_id, None)

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
            evicted = await self._registry.evict_idle()
            if evicted:
                # Drop smoothers for sessions that were evicted
                active_ids = {st.stream_id for st in self._registry.all()}
                for sid in list(self._smoothers):
                    if sid not in active_ids:
                        self._smoothers.pop(sid, None)
            return
        for st in sessions:
            try:
                await self._maybe_predict(st)
            except Exception as exc:
                log.exception("Predicting for stream %s failed: %s", st.stream_id, exc)
        evicted = await self._registry.evict_idle()
        if evicted:
            active_ids = {st.stream_id for st in self._registry.all()}
            for sid in list(self._smoothers):
                if sid not in active_ids:
                    self._smoothers.pop(sid, None)

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
            step_changed = st.step_changed_at == decision_t  # True on the first tick after a step change
            proc_id = int(st.procedure_id)
            step_num = int(st.step_number)
            stream_id = st.stream_id

            features, is_valid, qa = extract_features(
                pupil_t=arrays["pupil_t"],
                pupil_eye=arrays["pupil_eye"],
                pupil_diam_mm=arrays["pupil_diam"],
                blink_durations_s=arrays["blink_durations_s"],
                fix_durations_s=arrays["fix_durations_s"],
                fix_dispersion=arrays["fix_dispersion"],
                baseline=baseline,
                procedure_id=proc_id,
                step_number=step_num,
                cumulative_session_time_s=cumulative,
                window_len_s=settings.window_len_s,
                expected_pupil_rate_hz_per_eye=settings.expected_pupil_rate_hz_per_eye,
                min_data_yield=settings.min_data_yield,
            )

        # Do not hold session lock during model / HTTP inference — blocks pupil & fixation ingress.
        try:
            if settings.fargate_inference_url:
                raw_label, proba = await predict_remote(stream_id, decision_t, features)
                source = "remote"
            else:
                if self._predictor is None:
                    log.warning("No local predictor and no FARGATE_INFERENCE_URL set; skipping.")
                    return
                raw_label, proba = self._predictor.predict(features)
                source = "local"
        except Exception:
            log.exception("Inference failed for stream %s", stream_id)
            return

        # Apply workload smoother: 30-second stability gate + direction guard.
        smoother = self._get_smoother(stream_id)
        if step_changed:
            # Clear the pending candidate so the new step's predictions
            # accumulate fresh, but keep the currently shown level.
            smoother.reset_candidate()
        stable_label = smoother.update(raw_label)

        # Sanitize NaN/inf values in the response payload (the predictor has
        # already consumed `features` directly, so NaNs went through HGB
        # natively; here we convert them to None for JSON serialization).
        feature_values_safe = _json_safe(features)
        qa_safe = _json_safe(qa)

        prediction: dict = {
            "stream_id": stream_id,
            "decision_time": decision_t,
            "procedure_id": proc_id,
            "step_number": step_num,
            "cumulative_session_time_s": float(cumulative),
            # raw_label  = direct model output (changes every second)
            # workload_label = smoothed level shown to the operator
            "raw_workload_label": raw_label,
            "workload_label": stable_label,
            "workload_proba": proba,
            "smoother_state": smoother.state_dict(),
            "feature_values": feature_values_safe,
            "inference_source": source,
            "is_valid_window": bool(is_valid),
            "notes": None if is_valid else "low data yield in window — prediction may be unreliable",
            "qa": qa_safe,
        }

        async with st.lock:
            st.last_prediction = prediction
            st.latest_prediction_at_wall = time.time()

        self._publish_sse(stream_id, prediction)
        await push_prediction_webhook(prediction)
