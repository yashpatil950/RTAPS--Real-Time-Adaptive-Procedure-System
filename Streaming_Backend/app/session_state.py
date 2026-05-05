"""Per-stream live state for the RTAPS workload pipeline.

A `SessionState` lives in memory for as long as one operator is running one
procedure. It holds:

  * three rolling buffers — pupil samples, blinks, fixations — sized to the
    feature window (`window_len_s`), trimmed every time new data lands;
  * a one-shot pupil-baseline tracker for the first `baseline_duration_s`
    of pupil data;
  * the latest UI state (procedure_id, step_number) reported by the frontend;
  * the most recent prediction (so HTTP / SSE clients can read it without
    waiting for the next inference tick).

There is no persistence — every prediction is computed live from the current
window and pushed onward immediately. Nothing is written to CSV on the live
path.
"""
from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional

import numpy as np

from app.feature_extractor import PupilBaseline


# --------------------------------------------------------------------------- #
# Tiny record types kept inside the deques (plain dataclasses → cheap)        #
# --------------------------------------------------------------------------- #


@dataclass
class _PupilRec:
    t: float
    eye_id: int
    diameter: float
    confidence: float


@dataclass
class _BlinkRec:
    t: float
    duration: float
    tracking_loss: bool


@dataclass
class _FixRec:
    t: float
    duration: float
    dispersion: float


# --------------------------------------------------------------------------- #
# Baseline tracker                                                            #
# --------------------------------------------------------------------------- #


class BaselineTracker:
    """Accumulates the first `baseline_duration_s` of confidence-filtered pupil
    samples per eye, then freezes a `PupilBaseline`. Live predictions are
    suppressed by `InferenceLoop` until `is_ready()` returns True.
    """

    def __init__(self, baseline_duration_s: float, min_confidence: float):
        self._baseline_duration_s = baseline_duration_s
        self._min_confidence = min_confidence
        self._started_at: Optional[float] = None
        self._samples_eye0: list[float] = []
        self._samples_eye1: list[float] = []
        self._baseline: Optional[PupilBaseline] = None

    def add(self, sample: _PupilRec) -> None:
        if self._baseline is not None:
            return
        if sample.confidence < self._min_confidence:
            return
        if self._started_at is None:
            self._started_at = sample.t
        if sample.t - self._started_at > self._baseline_duration_s:
            return
        if sample.eye_id == 0:
            self._samples_eye0.append(sample.diameter)
        else:
            self._samples_eye1.append(sample.diameter)

    def maybe_finalize(self, latest_t: float) -> bool:
        """Finalize if enough wall time has passed. Returns True if newly ready."""
        if self._baseline is not None or self._started_at is None:
            return False
        if latest_t - self._started_at < self._baseline_duration_s:
            return False
        e0 = float(np.mean(self._samples_eye0)) if self._samples_eye0 else math.nan
        e1 = float(np.mean(self._samples_eye1)) if self._samples_eye1 else math.nan
        finite = [b for b in (e0, e1) if not math.isnan(b)]
        mean_mm = float(np.mean(finite)) if finite else math.nan
        self._baseline = PupilBaseline(eye0_mm=e0, eye1_mm=e1, mean_mm=mean_mm)
        # Free the per-sample buffers — they're not needed after finalization.
        self._samples_eye0.clear()
        self._samples_eye1.clear()
        return True

    def is_ready(self) -> bool:
        return self._baseline is not None and not math.isnan(self._baseline.mean_mm)

    def baseline(self) -> Optional[PupilBaseline]:
        return self._baseline

    def started_at(self) -> Optional[float]:
        return self._started_at

    def seconds_remaining(self, latest_t: Optional[float]) -> Optional[float]:
        if self._baseline is not None:
            return 0.0
        if self._started_at is None or latest_t is None:
            return None
        remain = self._baseline_duration_s - (latest_t - self._started_at)
        return max(0.0, remain)


# --------------------------------------------------------------------------- #
# Per-stream live state                                                       #
# --------------------------------------------------------------------------- #


@dataclass
class SessionState:
    stream_id: str
    window_len_s: float
    baseline_duration_s: float
    min_confidence: float
    blink_tracking_loss_s: float

    procedure_id: Optional[int] = None
    step_number: Optional[int] = None
    step_id: Optional[int] = None
    participant_id: Optional[str] = None
    n_steps_total: Optional[int] = None

    session_started_at: Optional[float] = None
    step_changed_at: Optional[float] = None
    latest_pupil_t: Optional[float] = None
    latest_prediction_at_wall: Optional[float] = None
    last_seen_wall: float = field(default_factory=time.time)

    last_prediction: Optional[dict] = None  # serialized PredictionResponse

    # Plain Python deques sized to ~ generous worst-case for a 10 s window.
    _pupil: Deque[_PupilRec] = field(default_factory=lambda: deque(maxlen=4000))
    _blinks: Deque[_BlinkRec] = field(default_factory=lambda: deque(maxlen=200))
    _fixations: Deque[_FixRec] = field(default_factory=lambda: deque(maxlen=400))

    baseline: BaselineTracker = field(init=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self) -> None:
        self.baseline = BaselineTracker(self.baseline_duration_s, self.min_confidence)

    # ---- ingress -------------------------------------------------------- #

    def add_pupil(self, samples: list[_PupilRec]) -> int:
        accepted = 0
        for s in samples:
            if s.confidence < self.min_confidence:
                continue
            self._pupil.append(s)
            self.baseline.add(s)
            self.latest_pupil_t = s.t if self.latest_pupil_t is None else max(self.latest_pupil_t, s.t)
            accepted += 1
        if self.latest_pupil_t is not None:
            self.baseline.maybe_finalize(self.latest_pupil_t)
            self._trim()
        self.last_seen_wall = time.time()
        return accepted

    def add_blinks(self, blinks: list[_BlinkRec]) -> int:
        accepted = 0
        for b in blinks:
            b.tracking_loss = b.tracking_loss or (b.duration >= self.blink_tracking_loss_s)
            self._blinks.append(b)
            accepted += 1
        self._trim()
        self.last_seen_wall = time.time()
        return accepted

    def add_fixations(self, fixations: list[_FixRec]) -> int:
        for f in fixations:
            self._fixations.append(f)
        self._trim()
        self.last_seen_wall = time.time()
        return len(fixations)

    def _trim(self) -> None:
        """Drop anything that left the window relative to the latest pupil_t."""
        if self.latest_pupil_t is None:
            return
        cutoff = self.latest_pupil_t - self.window_len_s
        while self._pupil and self._pupil[0].t < cutoff:
            self._pupil.popleft()
        while self._blinks and self._blinks[0].t < cutoff:
            self._blinks.popleft()
        while self._fixations and self._fixations[0].t < cutoff:
            self._fixations.popleft()

    # ---- ui state ------------------------------------------------------- #

    def mark_session_start(
        self,
        procedure_id: int,
        participant_id: Optional[str],
        n_steps_total: Optional[int],
    ) -> None:
        self.procedure_id = procedure_id
        self.participant_id = participant_id
        self.n_steps_total = n_steps_total
        self.session_started_at = self.latest_pupil_t  # may be None until first pupil
        self.step_number = None
        self.step_id = None
        self.step_changed_at = None

    def mark_step_change(self, step_number: int, step_id: Optional[int]) -> None:
        self.step_number = step_number
        self.step_id = step_id
        self.step_changed_at = self.latest_pupil_t

    def maybe_anchor_session_start(self) -> None:
        """If session_start arrived before any pupil, anchor it to the first
        pupil sample we received."""
        if self.session_started_at is None and self.latest_pupil_t is not None and self.procedure_id is not None:
            self.session_started_at = self.latest_pupil_t

    # ---- snapshot for the inference loop -------------------------------- #

    def window_arrays(self) -> dict[str, np.ndarray]:
        """Return numpy arrays for the current window slice."""
        if not self._pupil:
            pt = pe = pd_ = np.empty(0)
        else:
            arr = np.array([(r.t, r.eye_id, r.diameter) for r in self._pupil], dtype=float)
            pt, pe, pd_ = arr[:, 0], arr[:, 1].astype(int), arr[:, 2]

        if self._blinks:
            bd = np.array([b.duration for b in self._blinks if not b.tracking_loss], dtype=float)
        else:
            bd = np.empty(0)

        if self._fixations:
            fd = np.array([f.duration for f in self._fixations], dtype=float)
            fdisp = np.array([f.dispersion for f in self._fixations], dtype=float)
        else:
            fd = np.empty(0)
            fdisp = np.empty(0)

        return {
            "pupil_t": pt,
            "pupil_eye": pe,
            "pupil_diam": pd_,
            "blink_durations_s": bd,
            "fix_durations_s": fd,
            "fix_dispersion": fdisp,
        }

    def is_ready_for_inference(self) -> bool:
        return (
            self.procedure_id is not None
            and self.step_number is not None
            and self.session_started_at is not None
            and self.latest_pupil_t is not None
            and (self.latest_pupil_t - self.session_started_at) >= self.window_len_s
            and self.baseline.is_ready()
        )

    def seconds_until_first_prediction(self) -> Optional[float]:
        if self.is_ready_for_inference():
            return 0.0
        bl_remain = self.baseline.seconds_remaining(self.latest_pupil_t)
        win_remain: Optional[float] = None
        if self.session_started_at is not None and self.latest_pupil_t is not None:
            win_remain = max(0.0, self.window_len_s - (self.latest_pupil_t - self.session_started_at))
        candidates = [x for x in (bl_remain, win_remain) if x is not None]
        return max(candidates) if candidates else None

    # ---- introspection -------------------------------------------------- #

    def view(self) -> dict:
        bl = self.baseline.baseline()
        return {
            "stream_id": self.stream_id,
            "procedure_id": self.procedure_id,
            "step_number": self.step_number,
            "participant_id": self.participant_id,
            "session_started_at": self.session_started_at,
            "latest_pupil_t": self.latest_pupil_t,
            "latest_prediction_at": self.latest_prediction_at_wall,
            "pupil_samples_buffered": len(self._pupil),
            "blinks_buffered": len(self._blinks),
            "fixations_buffered": len(self._fixations),
            "baseline_ready": self.baseline.is_ready(),
            "baseline": (
                {"eye0_mm": bl.eye0_mm, "eye1_mm": bl.eye1_mm, "mean_mm": bl.mean_mm}
                if bl is not None
                else None
            ),
            "last_prediction": self.last_prediction,
        }

    def dashboard_snapshot(self) -> dict:
        """Dense JSON for the RTAPS live dashboard (eye preview + window metadata)."""
        base = self.view()
        lt = self.latest_pupil_t
        win_start = (lt - self.window_len_s) if lt is not None else None

        last_eye0: dict | None = None
        last_eye1: dict | None = None
        for r in reversed(self._pupil):
            if r.eye_id == 0 and last_eye0 is None:
                last_eye0 = {
                    "timestamp": r.t,
                    "diameter_mm": r.diameter,
                    "confidence": r.confidence,
                }
            elif r.eye_id == 1 and last_eye1 is None:
                last_eye1 = {
                    "timestamp": r.t,
                    "diameter_mm": r.diameter,
                    "confidence": r.confidence,
                }
            if last_eye0 is not None and last_eye1 is not None:
                break

        e0_pts = [{"t": r.t, "mm": r.diameter} for r in self._pupil if r.eye_id == 0]
        e1_pts = [{"t": r.t, "mm": r.diameter} for r in self._pupil if r.eye_id == 1]

        def _tail_sample(pts: list[dict], max_n: int = 120) -> list[dict]:
            if len(pts) <= max_n:
                return pts
            step = max(1, len(pts) // max_n)
            return pts[::step][-max_n:]

        qa = None
        lp = base.get("last_prediction")
        if isinstance(lp, dict) and "qa" in lp:
            qa = lp.get("qa")

        return {
            **base,
            "sliding_window": {
                "length_s": self.window_len_s,
                "start_timestamp": win_start,
                "end_timestamp": lt,
            },
            "latest_pupil_by_eye": {"0": last_eye0, "1": last_eye1},
            "pupil_series_eye0": _tail_sample(e0_pts),
            "pupil_series_eye1": _tail_sample(e1_pts),
            "baseline_phase": {
                "started_at_pupil_t": self.baseline.started_at(),
                "ready": self.baseline.is_ready(),
                "seconds_remaining_estimate": self.baseline.seconds_remaining(lt),
            },
            "inference_ready": self.is_ready_for_inference(),
            "last_prediction_qa": qa,
        }


# --------------------------------------------------------------------------- #
# Registry — one entry per active stream                                      #
# --------------------------------------------------------------------------- #


class SessionRegistry:
    def __init__(
        self,
        *,
        window_len_s: float,
        baseline_duration_s: float,
        min_confidence: float,
        blink_tracking_loss_s: float,
        idle_ttl_s: float,
    ):
        self._window_len_s = window_len_s
        self._baseline_duration_s = baseline_duration_s
        self._min_confidence = min_confidence
        self._blink_tracking_loss_s = blink_tracking_loss_s
        self._idle_ttl_s = idle_ttl_s
        self._streams: dict[str, SessionState] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, stream_id: str) -> SessionState:
        async with self._lock:
            st = self._streams.get(stream_id)
            if st is None:
                st = SessionState(
                    stream_id=stream_id,
                    window_len_s=self._window_len_s,
                    baseline_duration_s=self._baseline_duration_s,
                    min_confidence=self._min_confidence,
                    blink_tracking_loss_s=self._blink_tracking_loss_s,
                )
                self._streams[stream_id] = st
            return st

    def get(self, stream_id: str) -> Optional[SessionState]:
        return self._streams.get(stream_id)

    async def drop(self, stream_id: str) -> bool:
        async with self._lock:
            return self._streams.pop(stream_id, None) is not None

    def all(self) -> list[SessionState]:
        return list(self._streams.values())

    async def evict_idle(self) -> int:
        now = time.time()
        async with self._lock:
            stale = [sid for sid, st in self._streams.items() if (now - st.last_seen_wall) > self._idle_ttl_s]
            for sid in stale:
                self._streams.pop(sid, None)
            return len(stale)


# Re-export the record types so other modules can import them from one place.
PupilRec = _PupilRec
BlinkRec = _BlinkRec
FixRec = _FixRec
