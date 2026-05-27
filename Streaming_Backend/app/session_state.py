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
    """Per-session pupil baseline tracker — calibration-phase aware.

    Two modes:

    **Mode A — explicit calibration (preferred, new):** Frontend POSTs
    `/session/calibration_start` then waits `baseline_duration_s` (e.g.
    120 s) while showing a fixation cross with no task demands, then POSTs
    `/session/calibration_end`. While calibration is active, every
    confidence-filtered pupil sample is accumulated. On `calibration_end`,
    the baseline is **frozen** and predictions become enabled. The
    procedure does NOT start until calibration ends, so step 1 sees a
    fully-formed baseline from second 0.

    **Mode B — legacy auto-start (backwards-compatible):** If the
    frontend never calls `calibration_start`, the tracker falls back to
    the previous behavior: the first pupil sample seeds the start of an
    implicit calibration window, samples accumulate for
    `baseline_duration_s`, and finalize happens automatically. Used for
    integration with existing offline data / older clients.

    The two modes use the same accumulator buffer; what differs is the
    *gating* of `add()` and the way `is_ready()` is set.
    """

    def __init__(self, baseline_duration_s: float, min_confidence: float):
        self._baseline_duration_s = baseline_duration_s
        self._min_confidence = min_confidence
        # Mode A markers:
        # `_explicit_mode` flips to True as soon as the frontend says
        # calibration_start, even if no pupil samples have arrived yet.
        # `_calibration_started_at` is anchored to the FIRST pupil sample
        # received after the start signal (so we know when to count from
        # for the duration window).
        self._explicit_mode: bool = False
        self._calibration_started_at: Optional[float] = None
        self._calibration_ended_at: Optional[float] = None
        # Mode B implicit start:
        self._auto_started_at: Optional[float] = None
        # Accumulators:
        self._samples_eye0: list[float] = []
        self._samples_eye1: list[float] = []
        self._baseline: Optional[PupilBaseline] = None

    # ---- explicit calibration markers (Mode A) -------------------------- #

    def mark_calibration_start(self, t: Optional[float]) -> None:
        """Frontend signal: calibration phase has begun. Future pupil samples
        will be accumulated as baseline data.

        The operator's deliberate "sit still and look at the cross" baseline
        is the authoritative one — it always supersedes any Mode B baseline
        that may have already auto-finalized while the bridge was streaming
        but the frontend hadn't yet started the session. So this resets:
          * the previously-finalized baseline (if any),
          * any partial Mode B accumulation,
          * the accumulators themselves.
        """
        self._explicit_mode = True
        # If `t` is None we don't know the pupil clock yet — the first
        # incoming pupil sample will anchor `_calibration_started_at`.
        self._calibration_started_at = t
        self._calibration_ended_at = None
        self._auto_started_at = None
        self._baseline = None
        self._samples_eye0.clear()
        self._samples_eye1.clear()

    def mark_calibration_end(self, t: Optional[float]) -> bool:
        """Frontend signal: calibration phase has ended. Finalize the
        baseline using whatever samples are in the accumulator. Returns
        True if a baseline was successfully frozen.
        """
        self._calibration_ended_at = t
        # Defensive: if for some reason a baseline already exists (e.g. a
        # late-arriving auto-finalize from before calibration_start cleared
        # state), treat that as success rather than rejecting the calibration.
        if self._baseline is not None:
            return True
        return self._finalize_now()

    def calibrating(self) -> bool:
        """True iff explicit calibration has started but not ended."""
        return (
            self._explicit_mode
            and self._calibration_ended_at is None
            and self._baseline is None
        )

    # ---- sample ingress ------------------------------------------------- #

    def add(self, sample: _PupilRec) -> None:
        if self._baseline is not None:
            return
        if sample.confidence < self._min_confidence:
            return

        # Mode A: explicit calibration is in progress → accept samples,
        # anchoring `_calibration_started_at` to this first sample if the
        # frontend's `calibration_start` arrived before any pupil data.
        if self._explicit_mode and self._calibration_ended_at is None:
            if self._calibration_started_at is None:
                self._calibration_started_at = sample.t
            self._accumulate(sample)
            return

        # Mode A finalized (calibration_ended_at set) → samples should
        # belong to procedure, NOT to the baseline. Ignore for baseline
        # purposes (they still get appended to the rolling pupil deque
        # elsewhere).
        if self._explicit_mode and self._calibration_ended_at is not None:
            return

        # Mode B (legacy): no explicit calibration. Accumulate from first
        # sample for baseline_duration_s.
        if self._auto_started_at is None:
            self._auto_started_at = sample.t
        if sample.t - self._auto_started_at > self._baseline_duration_s:
            return
        self._accumulate(sample)

    def _accumulate(self, sample: _PupilRec) -> None:
        if sample.eye_id == 0:
            self._samples_eye0.append(sample.diameter)
        else:
            self._samples_eye1.append(sample.diameter)

    # ---- finalization --------------------------------------------------- #

    def maybe_finalize(self, latest_t: float) -> bool:
        """Mode B auto-finalize: returns True if newly ready.

        For Mode A, finalization happens explicitly via mark_calibration_end().
        """
        if self._baseline is not None:
            return False
        # Don't auto-finalize during explicit calibration — wait for the end signal.
        if self._explicit_mode:
            return False
        if self._auto_started_at is None:
            return False
        if latest_t - self._auto_started_at < self._baseline_duration_s:
            return False
        return self._finalize_now()

    def _finalize_now(self) -> bool:
        e0 = float(np.mean(self._samples_eye0)) if self._samples_eye0 else math.nan
        e1 = float(np.mean(self._samples_eye1)) if self._samples_eye1 else math.nan
        finite = [b for b in (e0, e1) if not math.isnan(b)]
        mean_mm = float(np.mean(finite)) if finite else math.nan
        if math.isnan(mean_mm):
            # No usable samples → keep waiting (Mode A may receive more data
            # before user closes; Mode B effectively retries on next sample).
            return False
        self._baseline = PupilBaseline(eye0_mm=e0, eye1_mm=e1, mean_mm=mean_mm)
        self._samples_eye0.clear()
        self._samples_eye1.clear()
        return True

    # ---- introspection -------------------------------------------------- #

    def is_ready(self) -> bool:
        return self._baseline is not None and not math.isnan(self._baseline.mean_mm)

    def baseline(self) -> Optional[PupilBaseline]:
        return self._baseline

    def started_at(self) -> Optional[float]:
        """Whichever start marker is active (explicit takes precedence)."""
        if self._explicit_mode:
            return self._calibration_started_at
        return self._auto_started_at

    def seconds_remaining(self, latest_t: Optional[float]) -> Optional[float]:
        if self._baseline is not None:
            return 0.0
        start = self.started_at()
        if start is None or latest_t is None:
            return None
        remain = self._baseline_duration_s - (latest_t - start)
        return max(0.0, remain)

    def mode(self) -> str:
        """Reporting helper: 'calibration_phase' if explicit Mode A is in use,
        'auto' if implicit Mode B, '' if no samples have arrived yet."""
        if self._explicit_mode:
            return "calibration_phase"
        if self._auto_started_at is not None:
            return "auto"
        return ""

    def accumulator_counts(self) -> tuple[int, int]:
        """How many baseline-accumulator samples currently held for each eye.
        Used by the calibration_end diagnostic to distinguish 'no samples
        ever arrived' from 'samples arrived but were dropped by Mode B
        because baseline was already finalized'."""
        return len(self._samples_eye0), len(self._samples_eye1)

    def explicit_active(self) -> bool:
        """True iff calibration_start has put the tracker into Mode A."""
        return self._explicit_mode


# --------------------------------------------------------------------------- #
# Per-stream live state                                                       #
# --------------------------------------------------------------------------- #


@dataclass
class SessionState:
    stream_id: str
    # Per-feature window lengths. `window_len_s` is the PUPIL window
    # (the "primary" decision window — used for PCPS, data yield, etc.).
    # `fixation_window_len_s` and `blink_window_len_s` are typically longer
    # (30 s in v4) because fixation/blink events are sparse and need more
    # history for stable estimates. Trim cutoffs are applied per-buffer so
    # data isn't dropped too early.
    window_len_s: float
    fixation_window_len_s: float
    blink_window_len_s: float
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
    calibration_started_at: Optional[float] = None
    calibration_ended_at: Optional[float] = None
    latest_pupil_t: Optional[float] = None
    latest_prediction_at_wall: Optional[float] = None
    last_seen_wall: float = field(default_factory=time.time)

    last_prediction: Optional[dict] = None  # serialized PredictionResponse

    # Running totals — never trimmed. Useful for diagnosing "are fixations
    # even reaching the backend?" when the rolling buffer is empty (sparse
    # events get trimmed past the 30 s window).
    pupil_received_total: int = 0
    blinks_received_total: int = 0
    fixations_received_total: int = 0
    last_fixation_received_at: Optional[float] = None  # wall clock
    last_blink_received_at: Optional[float] = None     # wall clock

    # Plain Python deques sized to ~ generous worst-case for the longest
    # per-feature window (blink/fixation = 30 s).
    _pupil: Deque[_PupilRec] = field(default_factory=lambda: deque(maxlen=4000))
    _blinks: Deque[_BlinkRec] = field(default_factory=lambda: deque(maxlen=400))
    # NOTE: fixations are stored in an insertion-ordered dict keyed by
    # `start_timestamp` (the fixation's onset, which is unique per fixation
    # in Pupil's clock). This is required because Pupil Capture's Online
    # Fixation Detector publishes multiple events for the SAME fixation as
    # it progresses (each with the same start_timestamp but growing
    # `duration` and growing `dispersion`). Keeping every event in a plain
    # deque produced ~3× more "fixation" records per 30-second window than
    # the training data had, with the means of both `duration` and
    # `dispersion` biased low — which the model read as "extremely focused
    # gaze" and over-predicted `high` workload. By upserting on
    # start_timestamp we collapse those multi-emit events to one record per
    # fixation, carrying the FINAL (most complete) values — matching the
    # one-row-per-fixation shape of `fixations_clean.parquet` at training
    # time.
    _fixations: dict[float, "_FixRec"] = field(default_factory=dict)
    _fixations_max: int = field(default=1600, init=False)

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
        self.pupil_received_total += accepted
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
        self.blinks_received_total += accepted
        if accepted:
            self.last_blink_received_at = time.time()
        self._trim()
        self.last_seen_wall = time.time()
        return accepted

    def add_fixations(self, fixations: list[_FixRec]) -> int:
        # Upsert by start_timestamp. Pupil's Online Fixation Detector
        # emits multiple events per fixation as it progresses (same
        # start_timestamp, growing duration/dispersion). The last event for
        # a given fixation carries the most complete values, so we
        # overwrite earlier partial-state records. Net result: one record
        # per real fixation — same shape as the training data.
        for f in fixations:
            # Re-insert (pop + set) so the dict's insertion order tracks
            # *latest* arrival rather than the first one. That keeps the
            # head-trim correct (oldest fixation onset gets evicted first).
            self._fixations.pop(f.t, None)
            self._fixations[f.t] = f
        n = len(fixations)
        self.fixations_received_total += n
        if n:
            self.last_fixation_received_at = time.time()
        # Hard cap to bound memory under bizarre conditions (e.g. clock
        # jumps); time-based trim below is the normal eviction path.
        while len(self._fixations) > self._fixations_max:
            self._fixations.pop(next(iter(self._fixations)))
        self._trim()
        self.last_seen_wall = time.time()
        return n

    def _trim(self) -> None:
        """Drop anything that left ITS OWN window relative to the latest pupil_t.

        v4 uses different windows per feature group:
          pupil    → 10 s
          fixation → 30 s
          blink    → 30 s

        Using a single 10 s cutoff would discard fixations and blinks that
        are still inside their (longer) windows — sparse events would then
        present as NaN feature values in the UI, which is what `the fixation
        data is blank in the UI` was reporting.
        """
        if self.latest_pupil_t is None:
            return
        pupil_cutoff = self.latest_pupil_t - self.window_len_s
        blink_cutoff = self.latest_pupil_t - self.blink_window_len_s
        fix_cutoff = self.latest_pupil_t - self.fixation_window_len_s
        while self._pupil and self._pupil[0].t < pupil_cutoff:
            self._pupil.popleft()
        while self._blinks and self._blinks[0].t < blink_cutoff:
            self._blinks.popleft()
        # Insertion-ordered dict: the head is the oldest start_timestamp.
        # Pop from the head until the next start_timestamp is inside the
        # fixation window.
        while self._fixations:
            first_t = next(iter(self._fixations))
            if first_t < fix_cutoff:
                self._fixations.pop(first_t)
            else:
                break

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

    def mark_calibration_start(self) -> None:
        """Frontend signal: calibration phase has begun. Baseline accumulator
        gets reset and will accept samples until calibration_end is received."""
        self.baseline.mark_calibration_start(self.latest_pupil_t)
        self.calibration_started_at = self.latest_pupil_t

    def mark_calibration_end(self) -> bool:
        """Frontend signal: calibration phase has ended. Freezes the baseline.
        Returns True if a baseline was successfully frozen, False if not
        enough samples were collected."""
        ok = self.baseline.mark_calibration_end(self.latest_pupil_t)
        self.calibration_ended_at = self.latest_pupil_t
        # Anchor session_started_at to the moment calibration ended — the
        # procedure timer starts here, so step-1 windows have a full clean
        # pre-history (the baseline period).
        if self.session_started_at is None:
            self.session_started_at = self.latest_pupil_t
        return ok

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
            fd = np.array([f.duration for f in self._fixations.values()], dtype=float)
            fdisp = np.array([f.dispersion for f in self._fixations.values()], dtype=float)
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
            "calibration_started_at": self.calibration_started_at,
            "calibration_ended_at": self.calibration_ended_at,
            "calibrating": self.baseline.calibrating(),
            "baseline_mode": self.baseline.mode(),
            "latest_pupil_t": self.latest_pupil_t,
            "latest_prediction_at": self.latest_prediction_at_wall,
            "pupil_samples_buffered": len(self._pupil),
            "blinks_buffered": len(self._blinks),
            "fixations_buffered": len(self._fixations),
            # Running totals — survive deque trimming. Use these to verify
            # that fixations/blinks are reaching the backend at all (a buffer
            # of 0 could just mean "no recent events", but a TOTAL of 0 after
            # many seconds means the bridge / Online Fixation Detector plugin
            # isn't sending anything).
            "pupil_received_total": self.pupil_received_total,
            "blinks_received_total": self.blinks_received_total,
            "fixations_received_total": self.fixations_received_total,
            "last_blink_received_at": self.last_blink_received_at,
            "last_fixation_received_at": self.last_fixation_received_at,
            "baseline_ready": self.baseline.is_ready(),
            "baseline": (
                {"eye0_mm": bl.eye0_mm, "eye1_mm": bl.eye1_mm, "mean_mm": bl.mean_mm}
                if bl is not None
                else None
            ),
            "baseline_seconds_remaining": self.baseline.seconds_remaining(self.latest_pupil_t),
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
        fixation_window_len_s: float,
        blink_window_len_s: float,
        baseline_duration_s: float,
        min_confidence: float,
        blink_tracking_loss_s: float,
        idle_ttl_s: float,
    ):
        self._window_len_s = window_len_s
        self._fixation_window_len_s = fixation_window_len_s
        self._blink_window_len_s = blink_window_len_s
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
                    fixation_window_len_s=self._fixation_window_len_s,
                    blink_window_len_s=self._blink_window_len_s,
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
