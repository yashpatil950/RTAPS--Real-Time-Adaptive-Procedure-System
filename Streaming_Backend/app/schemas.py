"""Wire formats for the live RTAPS streaming backend.

Two senders feed this service:

  * the **Pupil Capture bridge** (`pupil_capture_bridge.py`) forwards three
    ZMQ topics (`pupil`, `blinks`, `fixations`) as `PupilIngestRequest`,
    `BlinkIngestRequest`, and `FixationIngestRequest` POSTs;
  * the **RTAPS frontend** sends `SessionStartRequest`, `StepChangeRequest`,
    and `SessionEndRequest` whenever the operator starts a procedure, moves
    to a new step, or completes / aborts the session.

All eye-tracking events carry the timestamp that Pupil Capture emitted with
them (`pupil_timestamp`, seconds, monotonic). UI events are stamped on the
backend at receive time using the most recent pupil-clock value, so every
piece of state in the system shares the same time axis. No clock conversion
is asked of the frontend.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Eye-tracking events (from Pupil Capture)                                    #
# --------------------------------------------------------------------------- #


class PupilSample(BaseModel):
    timestamp: float = Field(..., description="Pupil Capture pupil_timestamp (s)")
    eye_id: int = Field(..., ge=0, le=1)
    diameter: float = Field(..., ge=0.0, description="Diameter in mm (3D model preferred)")
    confidence: float = Field(..., ge=0.0, le=1.0)


class BlinkEvent(BaseModel):
    start_timestamp: float = Field(..., description="Pupil clock, blink onset (s)")
    duration: float = Field(..., ge=0.0, description="Duration in seconds")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class FixationEvent(BaseModel):
    start_timestamp: float = Field(..., description="Pupil clock, fixation onset (s)")
    duration: float = Field(..., ge=0.0, description="Duration in seconds")
    dispersion: float = Field(default=0.0, ge=0.0, description="Dispersion in degrees")
    norm_x: float = Field(default=0.5, description="Normalized x in [0, 1]")
    norm_y: float = Field(default=0.5, description="Normalized y in [0, 1]")


class PupilIngestRequest(BaseModel):
    stream_id: str
    samples: list[PupilSample] = Field(..., min_length=1)


class BlinkIngestRequest(BaseModel):
    stream_id: str
    blinks: list[BlinkEvent] = Field(..., min_length=1)


class FixationIngestRequest(BaseModel):
    stream_id: str
    fixations: list[FixationEvent] = Field(..., min_length=1)


# --------------------------------------------------------------------------- #
# Session/UI events (from the RTAPS frontend)                                 #
# --------------------------------------------------------------------------- #


class SessionStartRequest(BaseModel):
    stream_id: str
    procedure_id: int = Field(..., ge=1, le=3, description="1=Centrifuge, 2=Column Flushing, 3=Pressure Testing")
    participant_id: str | None = None
    n_steps_total: int | None = None


class StepChangeRequest(BaseModel):
    stream_id: str
    step_number: int = Field(..., ge=1)
    step_id: int | None = None


class CalibrationStartRequest(BaseModel):
    """Frontend signal: operator is now sitting calmly looking at the
    fixation cross. Backend begins accumulating pupil samples into the
    baseline. The procedure does NOT yet start."""

    stream_id: str


class CalibrationEndRequest(BaseModel):
    """Frontend signal: calibration period is over. Backend freezes the
    baseline. The procedure can now begin and step 1 will see a fully
    formed baseline."""

    stream_id: str


class SessionEndRequest(BaseModel):
    stream_id: str


# --------------------------------------------------------------------------- #
# Responses                                                                   #
# --------------------------------------------------------------------------- #


class IngestResponse(BaseModel):
    stream_id: str
    accepted: int
    pupil_samples_buffered: int = 0
    blinks_buffered: int = 0
    fixations_buffered: int = 0
    baseline_ready: bool = False
    seconds_until_first_prediction: float | None = None


class SessionAck(BaseModel):
    stream_id: str
    status: str
    message: str | None = None


class PredictionResponse(BaseModel):
    stream_id: str
    decision_time: float
    procedure_id: int
    step_number: int
    cumulative_session_time_s: float
    # `workload_label` is the smoothed, displayable level (drives UI).
    # `raw_workload_label` is the unsmoothed per-second model output (for QA).
    workload_label: str
    raw_workload_label: str | None = None
    workload_proba: dict[str, float]
    smoother_state: dict[str, Any] | None = None
    feature_values: dict[str, float | int | None]
    inference_source: str = Field(..., description="'local' or 'remote'")
    is_valid_window: bool = True
    notes: str | None = None


class SessionStateView(BaseModel):
    """Debug view of a session's live state."""

    stream_id: str
    procedure_id: int | None
    step_number: int | None
    participant_id: str | None
    session_started_at: float | None
    calibration_started_at: float | None = None
    calibration_ended_at: float | None = None
    calibrating: bool = False
    baseline_mode: str = ""
    baseline_seconds_remaining: float | None = None
    latest_pupil_t: float | None
    latest_prediction_at: float | None
    pupil_samples_buffered: int
    blinks_buffered: int
    fixations_buffered: int
    baseline_ready: bool
    baseline: dict[str, float] | None
    last_prediction: PredictionResponse | None


class HealthResponse(BaseModel):
    status: str
    extras: dict[str, Any] = Field(default_factory=dict)
