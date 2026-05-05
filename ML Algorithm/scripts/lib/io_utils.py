"""Filesystem discovery, slug normalization, and Pupil/RTAPS file parsing."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import (
    LAPTOP_SHORT,
    LAPTOPS,
    PROCEDURE_ID_TO_SLUG,
    PROCEDURE_SLUGS,
    RAW_DATA_ROOT,
    STREAMING_FILENAME_TZ_OFFSET_HOURS,
)
from .sync import ClockAnchor

USER_DIR_RE = re.compile(r"^User_(\d+)_(.+)$", re.IGNORECASE)
STREAMING_DIR_RE = re.compile(r"^S(\d+)$", re.IGNORECASE)
TRIAL_DIR_RE = re.compile(r"^T(\d+)$", re.IGNORECASE)
STREAMING_FILE_RE = re.compile(
    r"^pupil_data_(?P<date>\d{8})_(?P<time>\d{6})\.csv$"
)


def slugify_procedure(raw: str) -> str | None:
    """Normalize a folder/procedure-name string to a canonical slug."""
    s = raw.lower().replace(" ", "_").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip("_")
    if "pressure" in s and "test" in s:
        return "pressure_testing"
    if "column" in s and "flush" in s:
        return "column_flushing"
    if "centrifuge" in s or re.fullmatch(r"cent\d*", s) or s.startswith("cent_"):
        return "centrifuge"
    if s in PROCEDURE_SLUGS:
        return s
    return None


def parse_procedure_name(name) -> tuple[int | None, int | None, str | None]:
    """Parse 'Centrifuge - Train 1' → (procedure_id, train_number, slug)."""
    if not isinstance(name, str) or not name.strip():
        return None, None, None
    slug = slugify_procedure(name.split(" - ")[0])
    train = None
    m = re.search(r"Train\s*(\d+)", name, re.IGNORECASE)
    if m:
        train = int(m.group(1))
    pid = next((k for k, v in PROCEDURE_ID_TO_SLUG.items() if v == slug), None)
    return pid, train, slug


def session_uid(laptop: str, user_id: str, procedure_slug: str) -> str:
    return f"{LAPTOP_SHORT.get(laptop, laptop.lower())}__{user_id}__{procedure_slug}"


@dataclass
class PupilRecording:
    laptop: str
    user_dir: Path
    user_id: str
    folder_procedure_slug: str
    info_path: Path
    anchor: ClockAnchor
    files_present: dict[str, bool]


def _discover_user_dirs(model_data_root: Path) -> Iterable[Path]:
    if not model_data_root.is_dir():
        return []
    out = []
    for child in sorted(model_data_root.iterdir()):
        if child.is_dir() and USER_DIR_RE.match(child.name):
            out.append(child)
    return out


def _find_model_data_dir(laptop_root: Path) -> Path | None:
    """Find the Model_Data subdir case-insensitively, picking exactly one path on disk."""
    if not laptop_root.is_dir():
        return None
    for child in laptop_root.iterdir():
        if child.is_dir() and child.name.lower() == "model_data":
            return child
    return None


def discover_pupil_recordings() -> list[PupilRecording]:
    """Walk all 3 laptops' Model_Data folders, collect Pupil recordings with info.player.json."""
    found: list[PupilRecording] = []
    seen_user_dirs: set[Path] = set()
    for laptop in LAPTOPS:
        mdr = _find_model_data_dir(RAW_DATA_ROOT / laptop)
        if mdr is None:
            continue
        for user_dir in _discover_user_dirs(mdr):
            resolved = user_dir.resolve()
            if resolved in seen_user_dirs:
                continue
            seen_user_dirs.add(resolved)
            m = USER_DIR_RE.match(user_dir.name)
            if not m:
                continue
            user_id, raw_proc = m.group(1), m.group(2)
            slug = slugify_procedure(raw_proc)
            if slug is None:
                print(f"  ! unknown procedure slug in {user_dir}, skipping")
                continue
            info = user_dir / "info.player.json"
            if not info.is_file():
                print(f"  ! no info.player.json in {user_dir}, skipping anchor")
                continue
            meta = json.loads(info.read_text())
            anchor = ClockAnchor(
                unix_at_pupil_start=float(meta["start_time_system_s"]),
                synced_at_pupil_start=float(meta["start_time_synced_s"]),
                pupil_duration_s=float(meta["duration_s"]),
            )
            files_present = {
                "pupil_positions": (user_dir / "pupil_positions.csv").is_file(),
                "fixations": (user_dir / "fixations.csv").is_file(),
                "blinks": (user_dir / "blinks.csv").is_file(),
                "gaze_positions": (user_dir / "gaze_positions.csv").is_file(),
                "world_timestamps": (user_dir / "world_timestamps.csv").is_file(),
            }
            found.append(
                PupilRecording(
                    laptop=laptop,
                    user_dir=user_dir,
                    user_id=user_id,
                    folder_procedure_slug=slug,
                    info_path=info,
                    anchor=anchor,
                    files_present=files_present,
                )
            )
    return found


@dataclass
class StreamingCapture:
    laptop: str
    csv_path: Path
    s_id: str
    t_id: str
    filename_unix: float


def discover_streaming_captures() -> list[StreamingCapture]:
    """Walk all 3 laptops' Streaming_data folders, collect pupil_data_*.csv with parsed timestamps."""
    out: list[StreamingCapture] = []
    for laptop in LAPTOPS:
        sdr = RAW_DATA_ROOT / laptop / "Streaming_data"
        if not sdr.is_dir():
            continue
        for s_dir in sorted(sdr.iterdir()):
            if not (s_dir.is_dir() and STREAMING_DIR_RE.match(s_dir.name)):
                continue
            s_id = STREAMING_DIR_RE.match(s_dir.name).group(1)
            for t_dir in sorted(s_dir.iterdir()):
                if not (t_dir.is_dir() and TRIAL_DIR_RE.match(t_dir.name)):
                    continue
                t_id = TRIAL_DIR_RE.match(t_dir.name).group(1)
                for f in sorted(t_dir.glob("pupil_data_*.csv")):
                    fm = STREAMING_FILE_RE.match(f.name)
                    if not fm:
                        continue
                    dt_local = datetime.strptime(
                        fm.group("date") + fm.group("time"), "%Y%m%d%H%M%S"
                    )
                    dt_utc = dt_local.replace(tzinfo=timezone.utc) - _local_offset()
                    out.append(
                        StreamingCapture(
                            laptop=laptop,
                            csv_path=f,
                            s_id=s_id,
                            t_id=t_id,
                            filename_unix=dt_utc.timestamp(),
                        )
                    )
    return out


def _local_offset():
    from datetime import timedelta

    return timedelta(hours=STREAMING_FILENAME_TZ_OFFSET_HOURS)


# --------------------------------------------------------------------------- #
# RTAPS sessions DB                                                           #
# --------------------------------------------------------------------------- #

DDB_VAL_RE = re.compile(r'\{\s*"(?P<typ>[NSBOOL]+)"\s*:\s*(?P<val>"[^"]*"|true|false|\d+)\s*\}')


def _ddb_unwrap(d):
    """Strip DynamoDB type wrappers from a parsed step entry."""
    out = {}
    for k, v in d.items():
        if isinstance(v, dict) and len(v) == 1:
            (typ, val), = v.items()
            if typ in {"N", "S"}:
                out[k] = float(val) if typ == "N" else str(val)
            elif typ == "BOOL":
                out[k] = bool(val)
            elif typ == "M":
                out[k] = _ddb_unwrap(val)
            else:
                out[k] = val
        else:
            out[k] = v
    return out


def _parse_steps_field(raw: str) -> list[dict]:
    """rtaps_sessions.csv stores steps as a DynamoDB-flavoured JSON array string."""
    arr = json.loads(raw)
    out = []
    for entry in arr:
        if isinstance(entry, dict) and "M" in entry:
            out.append(_ddb_unwrap(entry["M"]))
        elif isinstance(entry, dict):
            out.append(_ddb_unwrap(entry))
    for s in out:
        for k in ("stepId", "stepNumber", "timeSpentSec"):
            if k in s:
                s[k] = int(float(s[k]))
    return out


def load_rtaps_sessions(csv_path: Path) -> pd.DataFrame:
    """Return a tidy DataFrame; one row per session with parsed steps + UTC bounds."""
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().strip('"') for c in df.columns]
    df["completed_unix"] = (
        pd.to_datetime(df["completedAt"], utc=True).map(pd.Timestamp.timestamp)
    )
    df["totalTimeSec"] = pd.to_numeric(df["totalTimeSec"], errors="coerce").fillna(0).astype(int)
    df["session_start_unix"] = df["completed_unix"] - df["totalTimeSec"]
    df["session_end_unix"] = df["completed_unix"]

    parsed_pid, parsed_train, parsed_slug = [], [], []
    for n in df["procedureName"].astype(str):
        pid, train, slug = parse_procedure_name(n)
        parsed_pid.append(pid)
        parsed_train.append(train)
        parsed_slug.append(slug)
    df["parsed_procedure_id"] = parsed_pid
    df["parsed_train"] = parsed_train
    df["procedure_slug"] = parsed_slug

    parsed_steps = []
    for raw in df["steps"]:
        try:
            parsed_steps.append(_parse_steps_field(raw))
        except Exception as e:
            print(f"  ! failed to parse steps for sessionId={raw[:40]!r}: {e}")
            parsed_steps.append([])
    df["parsed_steps"] = parsed_steps
    df["n_steps"] = df["parsed_steps"].apply(len)
    return df
