#!/usr/bin/env python3
"""Live bridge: Pupil Capture -> RTAPS streaming backend.

Run this on the machine that has Pupil Capture open. It subscribes to three
ZMQ topics — `pupil`, `blinks`, `fixations` — and forwards each message to
the corresponding backend endpoint as small batched POSTs.

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


def _handle_blink(ctx: BridgeContext, payload: dict) -> None:
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


def _handle_fixation(ctx: BridgeContext, payload: dict) -> None:
    norm = payload.get("norm_pos", [0.5, 0.5])
    body = {
        "stream_id": ctx.stream_id,
        "fixations": [
            {
                "start_timestamp": float(payload.get("timestamp", time.time())),
                "duration": float(payload.get("duration", 0.0)) / 1000.0,  # Pupil emits ms
                "dispersion": float(payload.get("dispersion", 0.0)),
                "norm_x": float(norm[0]) if len(norm) > 0 else 0.5,
                "norm_y": float(norm[1]) if len(norm) > 1 else 0.5,
            }
        ],
    }
    _post(ctx, "/stream/fixations", body)


# --------------------------------------------------------------------------- #
# Main loop                                                                   #
# --------------------------------------------------------------------------- #


def main() -> int:
    args = _cli()
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
    for topic in ("pupil.", "blinks", "fixations"):
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
    try:
        while True:
            socks = dict(poller.poll(timeout=50))
            if sub in socks:
                topic, payload_raw = sub.recv_multipart()
                topic_str = topic.decode("utf-8")
                payload = msgpack.unpackb(payload_raw)
                if topic_str.startswith("pupil"):
                    batcher.add(payload)
                elif topic_str.startswith("blinks"):
                    _handle_blink(ctx, payload)
                elif topic_str.startswith("fixations"):
                    _handle_fixation(ctx, payload)
            batcher.maybe_flush()
    except KeyboardInterrupt:
        log.info("Interrupted; exiting.")
    finally:
        batcher.maybe_flush()
        sub.close()
        zctx.term()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
