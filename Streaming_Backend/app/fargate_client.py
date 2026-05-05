"""Optional remote-inference adapter.

When `FARGATE_INFERENCE_URL` is set, the live inference loop forwards the
**already-extracted feature vector** (not raw samples) to that URL and uses
the response as the prediction. This keeps the wire format small and the
serving side stateless.

Expected request:

    POST {FARGATE_INFERENCE_URL}
    Authorization: Bearer {API_TOKEN}        # optional
    Content-Type: application/json
    {
      "stream_id": "...",
      "decision_time": 12345.67,
      "features": { "<8 feature columns>": <value or null>, ... }
    }

Expected response:

    {
      "label": "low" | "medium" | "high",
      "proba": { "low": 0.x, "medium": 0.y, "high": 0.z }
    }

When the URL is unset the inference loop uses `LocalPredictor` instead. There
is no mock path: predictions are always either local or remote, never
synthetic.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

log = logging.getLogger(__name__)


async def predict_remote(
    stream_id: str,
    decision_time: float,
    features: dict[str, float | int | None],
) -> tuple[str, dict[str, float]]:
    if not settings.fargate_inference_url:
        raise RuntimeError("predict_remote called but FARGATE_INFERENCE_URL is not set.")

    headers = {"Content-Type": "application/json"}
    if settings.api_token:
        headers["Authorization"] = f"Bearer {settings.api_token}"

    payload: dict[str, Any] = {
        "stream_id": stream_id,
        "decision_time": decision_time,
        "features": features,
    }

    async with httpx.AsyncClient(timeout=settings.model_timeout_sec) as client:
        resp = await client.post(settings.fargate_inference_url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    label = str(data.get("label", "")).lower()
    proba_raw = data.get("proba", {}) or {}
    proba = {str(k): float(v) for k, v in proba_raw.items()}
    if not label or not proba:
        raise ValueError(f"Remote inference returned malformed response: {data}")
    return label, proba


async def push_prediction_webhook(prediction: dict[str, Any]) -> None:
    """Best-effort outbound POST to the optional prediction webhook."""
    if not settings.prediction_webhook_url:
        return
    headers = {"Content-Type": "application/json"}
    if settings.api_token:
        headers["Authorization"] = f"Bearer {settings.api_token}"
    try:
        async with httpx.AsyncClient(timeout=settings.model_timeout_sec) as client:
            await client.post(settings.prediction_webhook_url, json=prediction, headers=headers)
    except Exception as exc:
        log.warning("Prediction webhook POST failed: %s", exc)
