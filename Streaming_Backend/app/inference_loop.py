"""Asynchronous inference tick.

Once per `STRIDE_S` seconds we walk every active session, compute the 7
features over its current window, run the prediction (locally or remote),
pass the raw label through a WorkloadSmoother (configurable stability gate,
default 3 seconds, plus a direction guard), publish the stable result on the
per-session SSE channel, and optionally POST it to the configured frontend
webhook.

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
from app.feature_extractor import (
    FEATURE_TRAINING_BOUNDS,
    extract_features,
    sanitize_features_to_training_distribution,
)
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
        smoother_stability_s: Optional[int] = None,
    ):
        self._registry = registry
        self._predictor = predictor
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._sse_queues: dict[str, list[asyncio.Queue]] = {}
        # One WorkloadSmoother per active stream; created lazily.
        self._smoothers: dict[str, WorkloadSmoother] = {}
        # Fall back to the env-tunable setting (default 3 s) when caller
        # doesn't override. This keeps tests/explicit values working while
        # honouring WORKLOAD_SMOOTHER_STABILITY_S in production.
        self._smoother_stability_s = (
            smoother_stability_s
            if smoother_stability_s is not None
            else settings.workload_smoother_stability_s
        )
        # Per-stream prediction counter for periodic feature logging.
        self._tick_counts: dict[str, int] = {}
        # Per-stream last-seen step number. Used to detect step transitions
        # robustly: relying on `step_changed_at == decision_t` is fragile
        # because pupil samples arrive at 120 Hz and the timestamps drift
        # between the step-change POST and the next inference tick. This
        # comparison just looks at the step *number* and fires on any
        # change, including the very first prediction in a session.
        self._last_step_seen: dict[str, int] = {}

    def _get_smoother(self, stream_id: str) -> WorkloadSmoother:
        if stream_id not in self._smoothers:
            self._smoothers[stream_id] = WorkloadSmoother(
                self._smoother_stability_s, initial_level="low"
            )
        return self._smoothers[stream_id]

    def drop_smoother(self, stream_id: str) -> None:
        """Call when a session ends so the smoother's memory is freed."""
        self._smoothers.pop(stream_id, None)
        self._last_step_seen.pop(stream_id, None)

    # ---- lifecycle ------------------------------------------------------ #

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="inference-loop")
            log.info("Inference loop started (stride=%.2fs)", settings.stride_s)
            strat = settings.feature_sanitize_strategy
            if strat in ("mask", "clip"):
                bounds_str = "  ".join(
                    f"{n}={lo:g}..{hi:g}" for n, (lo, hi) in FEATURE_TRAINING_BOUNDS.items()
                )
                desc = (
                    "out-of-distribution → NaN (SimpleImputer fills with training median)"
                    if strat == "mask"
                    else "out-of-distribution → clamped to training envelope"
                )
                log.info(
                    "Feature sanitize strategy=%r (%s). Training bounds: %s",
                    strat, desc, bounds_str,
                )
            else:
                log.info(
                    "Feature sanitization DISABLED (FEATURE_SANITIZE_STRATEGY=off). "
                    "Raw features will be sent to the model — out-of-distribution "
                    "values may lock predictions to one class."
                )

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
            proc_id = int(st.procedure_id)
            step_num = int(st.step_number)
            stream_id = st.stream_id
            # Step transition is detected by comparing the current step
            # number against the last one we saw a prediction for on this
            # stream. Fires on the very first prediction of a session too
            # (since the cache starts empty), which is exactly what we want
            # — the smoother begins each step at "low".
            step_changed = self._last_step_seen.get(stream_id) != step_num
            self._last_step_seen[stream_id] = step_num

            features, is_valid, qa = extract_features(
                pupil_t=arrays["pupil_t"],
                pupil_eye=arrays["pupil_eye"],
                pupil_diam_mm=arrays["pupil_diam"],
                blink_durations_s=arrays["blink_durations_s"],
                fix_durations_s=arrays["fix_durations_s"],
                baseline=baseline,
                procedure_id=proc_id,
                step_number=step_num,
                cumulative_session_time_s=cumulative,
                window_len_s=settings.window_len_s,
                expected_pupil_rate_hz_per_eye=settings.expected_pupil_rate_hz_per_eye,
                min_data_yield=settings.min_data_yield,
            )

        # ---- Feature sanitization (train-serve skew guard) ----
        # Bring live features into the training-distribution envelope. The
        # default is "mask": out-of-distribution values become NaN, which
        # the training pipeline's SimpleImputer fills with the training
        # median (class-neutral). That effectively drops the offending
        # feature for the affected windows and lets the model fall back on
        # the features that actually carry class signal (pupil + blink).
        features_for_model, sanitize_actions, sanitize_deltas = (
            sanitize_features_to_training_distribution(
                features, strategy=settings.feature_sanitize_strategy,
            )
        )

        # ---- Periodic diagnostic logging ----
        log_every = settings.feature_log_every_n_ticks
        if log_every > 0:
            count = self._tick_counts.get(stream_id, 0) + 1
            self._tick_counts[stream_id] = count
            if count % log_every == 1:
                def _fmt(d: dict[str, float | int | None]) -> str:
                    parts = []
                    for n in (
                        "pupil_pcps_mean",
                        "pupil_diam_slope",
                        "blink_rate_30s",
                        "fixation_dur_mean_ms",
                    ):
                        v = d.get(n)
                        if v is None or (isinstance(v, float) and v != v):
                            parts.append(f"{n}=NaN")
                        else:
                            parts.append(f"{n}={float(v):.3f}")
                    return "  ".join(parts)
                log.info(
                    "[%s] tick=%d raw_features: %s", stream_id, count, _fmt(features)
                )
                if sanitize_actions:
                    detail = "  ".join(
                        (f"{k}=masked(was {sanitize_deltas[k]:.3f})"
                         if act == "masked"
                         else f"{k}=clipped(delta {sanitize_deltas[k]:+.3f})")
                        for k, act in sanitize_actions.items()
                    )
                    log.info(
                        "[%s] tick=%d sanitized: %s", stream_id, count, detail
                    )

        # Do not hold session lock during model / HTTP inference — blocks pupil & fixation ingress.
        try:
            if settings.fargate_inference_url:
                raw_label, proba = await predict_remote(stream_id, decision_t, features_for_model)
                source = "remote"
            else:
                if self._predictor is None:
                    log.warning("No local predictor and no FARGATE_INFERENCE_URL set; skipping.")
                    return
                raw_label, proba = self._predictor.predict(features_for_model)
                source = "local"
        except Exception:
            log.exception("Inference failed for stream %s", stream_id)
            return

        # Apply workload smoother: stability gate (default 3 s).
        # Every step starts at "low" — that's the operator-facing default
        # ("no extra guidance"). The smoother then needs `stability_window_s`
        # consecutive seconds of model "high" before it upgrades the display,
        # and the same number of consecutive seconds of "low" before it
        # downgrades back.
        smoother = self._get_smoother(stream_id)
        if step_changed:
            smoother.force_level("low")
            log.info(
                "[%s] step %d started — workload display reset to LOW (3 s of model 'high' required to upgrade)",
                stream_id, step_num,
            )
        stable_label = smoother.update(raw_label)

        # Sanitize NaN/inf values in the response payload (the predictor has
        # already consumed `features` directly, so NaNs went through HGB
        # natively; here we convert them to None for JSON serialization).
        # `feature_values` shows the RAW live values (what the sensor pipeline
        # actually computed). `feature_values_model_input` shows what was fed
        # to the model after clipping — these differ only when clipping kicked
        # in, in which case `feature_clip_deltas` carries the change.
        feature_values_safe = _json_safe(features)
        feature_values_model_safe = _json_safe(features_for_model)
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
            "feature_values_model_input": feature_values_model_safe,
            "feature_sanitize_actions": sanitize_actions,
            "feature_sanitize_deltas": sanitize_deltas,
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
