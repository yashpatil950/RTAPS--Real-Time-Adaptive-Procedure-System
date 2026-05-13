#!/usr/bin/env python3
"""Live bridge: Pupil Capture -> RTAPS streaming backend.

Run this on the machine that has Pupil Capture open. It subscribes to Pupil IPC
topics for pupil samples, blinks, and fixations, then forwards each message to
the matching backend endpoint as small POSTs.

Prerequisites in Pupil Capture:
  * **Network API** plugin enabled (default port 50020)
  * **Online Blink Detector** plugin enabled
  * **Online Fixation Detector** plugin enabled

Backend endpoints called:
  POST {backend}/stream/pupil         (every ~50 ms)
  POST {backend}/stream/blinks        (per blink event)
  POST {backend}/stream/fixations     (per fixation event)

Nothing is written to CSV. The flow is strictly:

    Pupil Capture --(ZMQ)--> bridge --(HTTP)--> backend --> ML model --> UI

Run:
    python pupil_capture_bridge.py --stream_id S001T001
"""
from __future__ import annotations

import argparse
import logging
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import msgpack
import requests
import zmq

log = logging.getLogger("pupil-bridge")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def _cli() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stream_id", required=True, help="Identifier for this Pupil session")
    ap.add_argument("--backend_url", default="http://127.0.0.1:8000",
                    help="Base URL of the streaming backend")
    ap.add_argument("--pupil_host", default="127.0.0.1")
    ap.add_argument("--pupil_port", type=int, default=50020)
    ap.add_argument("--min_confidence", type=float, default=0.6,
                    help="Drop pupil samples with confidence below this value")
    ap.add_argument("--pupil_batch_size", type=int, default=20,
                    help="Flush pupil batch when this many samples are buffered")
    ap.add_argument("--pupil_batch_ms", type=int, default=100,
                    help="Flush pupil batch at most this many ms after the first sample")
    ap.add_argument("--api_token", default="", help="Optional bearer token for the backend")
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Log ZMQ topics / fixation payload keys (for debugging missing fixations)",
    )
    return ap.parse_args()


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


@dataclass
class BridgeContext:
    stream_id: str
    backend_url: str
    headers: dict[str, str]
    session: requests.Session


def _unpack_payload(payload_raw: bytes) -> dict[str, Any]:
    """Decode msgpack from Pupil; normalize keys to str (some stacks emit bytes keys)."""
    try:
        obj = msgpack.unpackb(payload_raw, raw=False, strict_map_key=False)
    except TypeError:
        obj = msgpack.unpackb(payload_raw, raw=False)
    except Exception:
        obj = msgpack.unpackb(payload_raw)
    if not isinstance(obj, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in obj.items():
        key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
        out[key] = v
    return out


def _post(ctx: BridgeContext, path: str, body: dict[str, Any]) -> None:
    url = ctx.backend_url.rstrip("/") + path
    try:
        r = ctx.session.post(url, json=body, headers=ctx.headers, timeout=2.0)
        if r.status_code >= 400:
            log.warning("POST %s -> %s: %s", path, r.status_code, r.text[:200])
    except Exception as exc:
        log.warning("POST %s failed: %s", path, exc)


def _connect_pupil(host: str, port: int) -> tuple[zmq.Context, zmq.Socket, str]:
    """Resolve Pupil Capture's IPC SUB address via the REQ control channel."""
    ctx = zmq.Context.instance()
    req = ctx.socket(zmq.REQ)
    req.connect(f"tcp://{host}:{port}")
    req.send_string("SUB_PORT")
    sub_port = req.recv_string()
    req.close()
    sub = ctx.socket(zmq.SUB)
    sub.connect(f"tcp://{host}:{sub_port}")
    return ctx, sub, sub_port


# --------------------------------------------------------------------------- #
# Per-topic flushers                                                          #
# --------------------------------------------------------------------------- #


class PupilBatcher:
    """Buffers pupil samples briefly to keep the POST rate sane."""

    def __init__(self, ctx: BridgeContext, max_size: int, max_ms: int, min_confidence: float):
        self._ctx = ctx
        self._max_size = max_size
        self._max_seconds = max_ms / 1000.0
        self._min_confidence = min_confidence
        self._buffer: list[dict] = []
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def add(self, payload: dict) -> None:
        # Pupil v3 messages: 'diameter_3d' (mm) preferred over 'diameter' (px).
        diameter = payload.get("diameter_3d") or payload.get("diameter") or 0.0
        confidence = float(payload.get("confidence", 0.0))
        if confidence < self._min_confidence:
            return
        sample = {
            "timestamp": float(payload.get("timestamp", time.time())),
            "eye_id": int(payload.get("id", 0)),
            "diameter": float(diameter),
            "confidence": confidence,
        }
        with self._lock:
            if not self._buffer:
                self._opened_at = time.monotonic()
            self._buffer.append(sample)
            if len(self._buffer) >= self._max_size:
                self._flush_locked()

    def maybe_flush(self) -> None:
        with self._lock:
            if self._buffer and (time.monotonic() - self._opened_at) >= self._max_seconds:
                self._flush_locked()

    def _flush_locked(self) -> None:
        batch = self._buffer
        self._buffer = []
        if not batch:
            return
        _post(self._ctx, "/stream/pupil", {"stream_id": self._ctx.stream_id, "samples": batch})


def _handle_blink(ctx: BridgeContext, payload: dict[str, Any]) -> None:
    body = {
        "stream_id": ctx.stream_id,
        "blinks": [
            {
                "start_timestamp": float(payload.get("timestamp", time.time())),
                "duration": float(payload.get("duration", 0.0)),
                "confidence": float(payload.get("confidence", 1.0)),
            }
        ],
    }
    _post(ctx, "/stream/blinks", body)


def _handle_fixation(ctx: BridgeContext, payload: dict[str, Any]) -> None:
    """Map Pupil Online Fixation Detector payload → backend FixationEvent.

    Pupil docs use `start_timestamp` + `duration` (ms) + `norm_pos_x/y`; older
    builds used `timestamp` + `norm_pos`. Using wall time when timestamps are
    missing breaks the sliding window (fixations vanish from `window_arrays`).
    """
    ts = payload.get("start_timestamp")
    if ts is None:
        ts = payload.get("timestamp")
    if ts is None:
        log.warning("fixation message missing start_timestamp/timestamp; skip")
        return
    ts_f = float(ts)

    nx = payload.get("norm_pos_x")
    ny = payload.get("norm_pos_y")
    if nx is None or ny is None:
        norm = payload.get("norm_pos")
        if isinstance(norm, (list, tuple)) and len(norm) >= 2:
            nx, ny = float(norm[0]), float(norm[1])
        else:
            nx, ny = 0.5, 0.5
    else:
        nx, ny = float(nx), float(ny)

    dur_raw = float(payload.get("duration", 0.0))
    # Pupil Capture's Online Fixation Detector publishes duration in
    # milliseconds. Typical human fixation durations are 100-500 ms; some
    # third-party plugins emit seconds (0.1-0.5). Use a heuristic so both
    # forms produce a correct seconds value:
    #   - duration > 50  → assume milliseconds (divide by 1000)
    #   - duration ≤ 50  → assume already in seconds (no division)
    # A 50 ms fixation is below the perceptual threshold; a 50 s fixation
    # is biophysically impossible.
    dur_s = dur_raw / 1000.0 if dur_raw > 50.0 else dur_raw

    disp_raw = payload.get("dispersion")
    try:
        dispersion = float(disp_raw) if disp_raw is not None else 0.0
    except (TypeError, ValueError):
        dispersion = 0.0
    if dispersion < 0 or dispersion != dispersion:  # NaN
        dispersion = 0.0

    body = {
        "stream_id": ctx.stream_id,
        "fixations": [
            {
                "start_timestamp": ts_f,
                "duration": max(0.0, dur_s),
                "dispersion": dispersion,
                "norm_x": nx,
                "norm_y": ny,
            }
        ],
    }
    _post(ctx, "/stream/fixations", body)


# --------------------------------------------------------------------------- #
# Main loop                                                                   #
# --------------------------------------------------------------------------- #


def main() -> int:
    args = _cli()
    if args.verbose:
        log.setLevel(logging.DEBUG)
    headers = {"Content-Type": "application/json"}
    if args.api_token:
        headers["Authorization"] = f"Bearer {args.api_token}"
    ctx = BridgeContext(
        stream_id=args.stream_id,
        backend_url=args.backend_url,
        headers=headers,
        session=requests.Session(),
    )

    log.info("Connecting to Pupil Capture at %s:%d ...", args.pupil_host, args.pupil_port)
    zctx, sub, sub_port = _connect_pupil(args.pupil_host, args.pupil_port)
    log.info("Subscribed to SUB port %s", sub_port)
    # Prefix subscriptions — Pupil envelope topics vary by release.
    # Use `blink` / `fixation` prefixes so both singular and plural topic names match.
    # `notify.` is required for notification-shaped IPC messages (docs vs some builds use these).
    for topic in ("pupil.", "blink", "fixation", "notify."):
        sub.setsockopt_string(zmq.SUBSCRIBE, topic)

    batcher = PupilBatcher(
        ctx,
        max_size=args.pupil_batch_size,
        max_ms=args.pupil_batch_ms,
        min_confidence=args.min_confidence,
    )

    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)

    log.info("Forwarding to %s with stream_id=%s", args.backend_url, args.stream_id)
    log.info("Subscribed prefixes: pupil. / blink / fixation / notify.")
    log.info("NOTE: For fixation features to populate, you MUST enable the")
    log.info("      Online Fixation Detector plugin in Pupil Capture")
    log.info("      (Plugin Manager → Online Fixation Detector). Similarly for")
    log.info("      Online Blink Detector. Without these, no events arrive.")

    # Diagnostic counters — log a one-shot INFO message when the FIRST event
    # of each kind arrives. Then a periodic summary every 30 s.
    counts = {"pupil": 0, "blink": 0, "fixation": 0, "notify": 0, "other": 0}
    first_seen: dict[str, bool] = {"pupil": False, "blink": False, "fixation": False}
    last_summary = time.monotonic()

    def _record_and_log(kind: str) -> None:
        counts[kind] = counts.get(kind, 0) + 1
        if kind in first_seen and not first_seen[kind]:
            first_seen[kind] = True
            log.info("✓ First %s event received from Pupil Capture.", kind)

    try:
        while True:
            socks = dict(poller.poll(timeout=50))
            if sub in socks:
                parts = sub.recv_multipart()
                if len(parts) < 2:
                    continue
                topic_str = parts[0].decode("utf-8", errors="replace")
                # First frame after topic is always msgpack dict; extra frames are raw attachments.
                payload_raw = parts[1]
                payload = _unpack_payload(payload_raw)
                inner_topic = payload.get("topic")
                if isinstance(inner_topic, bytes):
                    inner_topic = inner_topic.decode("utf-8", errors="replace")
                elif inner_topic is not None and not isinstance(inner_topic, str):
                    inner_topic = str(inner_topic)
                if args.verbose and (
                    "fixat" in topic_str.lower()
                    or inner_topic in ("fixation", "fixations")
                    or (
                        isinstance(payload.get("subject"), str)
                        and "fixat" in payload["subject"].lower()
                    )
                ):
                    log.debug(
                        "zmq topic=%r frames=%d payload.topic=%r payload_keys=%s",
                        topic_str,
                        len(parts),
                        inner_topic,
                        sorted(payload.keys()),
                    )
                # Prefer payload["topic"] for fixation datums — envelope string can differ by Pupil version.
                fixation_inner = inner_topic in ("fixation", "fixations")
                if topic_str.startswith("pupil"):
                    _record_and_log("pupil")
                    batcher.add(payload)
                elif fixation_inner:
                    _record_and_log("fixation")
                    _handle_fixation(ctx, payload)
                elif topic_str.startswith("blink"):
                    _record_and_log("blink")
                    _handle_blink(ctx, payload)
                elif topic_str.startswith("fixation"):
                    _record_and_log("fixation")
                    _handle_fixation(ctx, payload)
                elif topic_str.startswith("notify."):
                    # Notifications use envelope ``notify.<subject>``; some builds encode fixation-like datums here.
                    subj = payload.get("subject")
                    if isinstance(subj, str) and "fixation" in subj.lower() and payload.get("start_timestamp") is not None:
                        _record_and_log("fixation")
                        _handle_fixation(ctx, payload)
                    else:
                        counts["notify"] += 1
                else:
                    counts["other"] += 1
            batcher.maybe_flush()

            # Periodic counter summary (every 30 s) so the operator can see
            # at a glance whether fixations are arriving.
            now = time.monotonic()
            if now - last_summary >= 30.0:
                last_summary = now
                log.info(
                    "Bridge counters (last 30 s+): pupil=%d  blink=%d  fixation=%d  notify=%d  other=%d",
                    counts.get("pupil", 0),
                    counts.get("blink", 0),
                    counts.get("fixation", 0),
                    counts.get("notify", 0),
                    counts.get("other", 0),
                )
                if counts.get("fixation", 0) == 0:
                    log.warning(
                        "No fixations received yet. Check Pupil Capture → Plugin Manager "
                        "→ Online Fixation Detector is enabled."
                    )
                if counts.get("blink", 0) == 0:
                    log.warning(
                        "No blinks received yet. Check Pupil Capture → Plugin Manager "
                        "→ Online Blink Detector is enabled."
                    )
    except KeyboardInterrupt:
        log.info("Interrupted; exiting. Final counts: %s", counts)
    finally:
        batcher.maybe_flush()
        sub.close()
        zctx.term()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
