"""Raw eye-data archival to Amazon S3 (with a local-disk fallback).

Each completed session is serialised to a single gzip-compressed JSON document
that holds the full pupil/blink/fixation streams plus session metadata, together
with a small companion ``.meta.json`` index object that carries only the
metadata (so the listing endpoint stays cheap).

When ``RAW_DATA_S3_BUCKET`` is set the documents are written to S3; otherwise
they are written under ``RAW_DATA_DIR`` on the backend's local disk. The two
back ends are otherwise interchangeable, so the system records raw data even
before an S3 bucket has been provisioned.
"""
from __future__ import annotations

import gzip
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from app.config import settings

log = logging.getLogger("rtaps.raw_store")

_DATA_SUFFIX = ".json.gz"
_META_SUFFIX = ".meta.json"

_s3 = None


def _s3_client():
    global _s3
    if _s3 is None:
        import boto3  # imported lazily so the backend runs without boto3 when archival is off

        _s3 = boto3.client("s3", region_name=settings.aws_region)
    return _s3


def use_s3() -> bool:
    return bool(settings.raw_data_s3_bucket)


def _safe(part: Any) -> str:
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(part))


def _data_key(meta: dict) -> str:
    # Filename encodes participant and procedure mode (adaptive/non-adaptive)
    # up front so each archived session is identifiable from its name alone,
    # e.g. raw_sessions/<participant>/<participant>__<mode>__<stream>__<ts>.json.gz.
    # (The file also stays under a per-participant folder for grouping.)
    ts = int(meta.get("persisted_at") or time.time())
    participant = _safe(meta.get("participant_id") or "unknown")
    mode = _safe(meta.get("mode") or "unknownmode")
    stream = _safe(meta.get("stream_id") or "session")
    return (
        f"{settings.raw_data_s3_prefix}/{participant}/"
        f"{participant}__{mode}__{stream}__{ts}{_DATA_SUFFIX}"
    )


def _meta_key(data_key: str) -> str:
    return data_key[: -len(_DATA_SUFFIX)] + _META_SUFFIX


def persist_session(dataset: dict) -> dict:
    """Serialise + store one session. Returns the lightweight index entry."""
    meta = dict(dataset.get("meta", {}))
    meta.setdefault("persisted_at", time.time())
    data_key = _data_key(meta)
    body = gzip.compress(json.dumps(dataset, separators=(",", ":")).encode("utf-8"))
    index = {
        **meta,
        "key": data_key,
        "size_bytes": len(body),
        "storage": "s3" if use_s3() else "local",
    }
    meta_blob = json.dumps(index).encode("utf-8")

    if use_s3():
        c = _s3_client()
        bucket = settings.raw_data_s3_bucket
        c.put_object(Bucket=bucket, Key=data_key, Body=body, ContentType="application/gzip")
        c.put_object(Bucket=bucket, Key=_meta_key(data_key), Body=meta_blob, ContentType="application/json")
    else:
        base = settings.raw_data_dir
        (base / Path(data_key).parent).mkdir(parents=True, exist_ok=True)
        (base / data_key).write_bytes(body)
        (base / _meta_key(data_key)).write_bytes(meta_blob)

    log.info("raw session archived: %s (%d bytes, %s)", data_key, len(body), index["storage"])
    return index


def list_sessions() -> list[dict]:
    """Return the lightweight index entry for every archived session."""
    out: list[dict] = []
    if use_s3():
        c = _s3_client()
        bucket = settings.raw_data_s3_bucket
        paginator = c.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{settings.raw_data_s3_prefix}/"):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(_META_SUFFIX):
                    try:
                        blob = c.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
                        out.append(json.loads(blob))
                    except Exception as exc:  # noqa: BLE001 - skip a corrupt index entry
                        log.warning("skipping unreadable index %s: %s", obj["Key"], exc)
    else:
        base = settings.raw_data_dir
        if base.exists():
            for p in base.rglob(f"*{_META_SUFFIX}"):
                try:
                    out.append(json.loads(p.read_text()))
                except Exception as exc:  # noqa: BLE001
                    log.warning("skipping unreadable index %s: %s", p, exc)
    out.sort(key=lambda x: x.get("persisted_at", 0), reverse=True)
    return out


def presign_url(data_key: str, expires_in: int = 3600) -> Optional[str]:
    """Presigned S3 GET URL for the raw file, or None when stored locally."""
    if not use_s3():
        return None
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.raw_data_s3_bucket, "Key": data_key},
        ExpiresIn=expires_in,
    )


def local_path(data_key: str) -> Optional[Path]:
    """Resolved on-disk path for a local raw file, or None (guards traversal)."""
    if use_s3():
        return None
    base = settings.raw_data_dir.resolve()
    p = (base / data_key).resolve()
    if base != p and base not in p.parents:
        return None
    return p if p.exists() else None


def delete_session(data_key: str) -> bool:
    """Delete a raw file and its index entry. Returns True if anything was removed."""
    meta_key = _meta_key(data_key) if data_key.endswith(_DATA_SUFFIX) else data_key + _META_SUFFIX
    if use_s3():
        c = _s3_client()
        bucket = settings.raw_data_s3_bucket
        c.delete_object(Bucket=bucket, Key=data_key)
        c.delete_object(Bucket=bucket, Key=meta_key)
        return True
    removed = False
    base = settings.raw_data_dir
    for key in (data_key, meta_key):
        p = base / key
        if p.exists():
            p.unlink()
            removed = True
    return removed
