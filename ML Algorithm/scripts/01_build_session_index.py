#!/usr/bin/env python3
"""Stage 1: build the master session catalog.

Walks all 3 laptops' `Model_Data/` and `Streaming_data/` trees, parses the
RTAPS UI session log, parses procedures.js for per-step thresholds, and
joins them on UTC wall-clock overlap.

Outputs (under `ML Algorithm/data/_processed/`):
  - session_index.csv       one row per discovered session (Pupil export ± streaming CSV)
  - procedure_steps.csv     (procedure_id, step_id, step_number, time_threshold_s)

Run:
  python "ML Algorithm/scripts/01_build_session_index.py"
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import (  # noqa: E402
    LAPTOP_SHORT,
    MATCH_DURATION_RATIO_HIGH,
    MATCH_DURATION_RATIO_OK,
    MATCH_OVERLAP_HIGH,
    MATCH_OVERLAP_MIN,
    PROCEDURES_JS,
    PROCESSED_ROOT,
    RTAPS_SESSIONS_CSV,
    STREAMING_FILENAME_TOLERANCE_S,
)
from lib.io_utils import (  # noqa: E402
    PupilRecording,
    StreamingCapture,
    discover_pupil_recordings,
    discover_streaming_captures,
    load_rtaps_sessions,
    session_uid,
)
from lib.procedures_parser import parse_procedures_js  # noqa: E402
from lib.sync import overlap_fraction, overlap_seconds  # noqa: E402

# --------------------------------------------------------------------------- #
# Matching                                                                    #
# --------------------------------------------------------------------------- #


@dataclass
class RtapsMatch:
    rtaps_row: pd.Series
    overlap_s: float
    overlap_frac: float
    duration_ratio: float
    confidence: str  # high | medium | low


def _classify_match(overlap_frac: float, dur_ratio: float) -> str | None:
    lo, hi = MATCH_DURATION_RATIO_HIGH
    if overlap_frac >= MATCH_OVERLAP_HIGH and lo <= dur_ratio <= hi:
        return "high"
    lo2, hi2 = MATCH_DURATION_RATIO_OK
    if overlap_frac >= MATCH_OVERLAP_MIN and lo2 <= dur_ratio <= hi2:
        return "medium"
    if overlap_frac >= 0.3:
        return "low"
    return None


def _match_rtaps_for_interval(
    procedure_slug: str,
    start_unix: float,
    end_unix: float,
    duration_s: float,
    rtaps: pd.DataFrame,
    excluded_ids: set[str],
) -> RtapsMatch | None:
    candidates = rtaps[
        (rtaps["procedure_slug"] == procedure_slug)
        & (~rtaps["sessionId"].isin(excluded_ids))
    ]
    best: RtapsMatch | None = None
    for _, row in candidates.iterrows():
        ov = overlap_seconds(
            start_unix, end_unix, row["session_start_unix"], row["session_end_unix"]
        )
        if ov <= 0:
            continue
        ov_frac = overlap_fraction(
            start_unix, end_unix, row["session_start_unix"], row["session_end_unix"]
        )
        durs = (max(duration_s, 1e-6), max(float(row["totalTimeSec"]), 1e-6))
        dur_ratio = max(durs) / min(durs)
        conf = _classify_match(ov_frac, dur_ratio)
        if conf is None:
            continue
        if best is None or ov_frac > best.overlap_frac:
            best = RtapsMatch(row, ov, ov_frac, dur_ratio, conf)
    return best


def _match_streaming_for_pupil(
    rec: PupilRecording,
    streams: list[StreamingCapture],
    used_streams: set[str],
) -> StreamingCapture | None:
    """Pair a Pupil export to a streaming CSV by laptop + filename UTC time."""
    best = None
    best_diff = STREAMING_FILENAME_TOLERANCE_S
    for s in streams:
        if s.laptop != rec.laptop or str(s.csv_path) in used_streams:
            continue
        diff = abs(s.filename_unix - rec.anchor.unix_at_pupil_start)
        if diff <= best_diff:
            best_diff = diff
            best = s
    return best


# --------------------------------------------------------------------------- #
# Row builders                                                                #
# --------------------------------------------------------------------------- #


def _row_skeleton() -> dict:
    return {
        "session_uid": "",
        "source": "",
        "laptop": "",
        "laptop_short": "",
        "user_dir": "",
        "user_id": "",
        "procedure_slug": "",
        "procedure_id": pd.NA,
        "pupil_export_dir": "",
        "pupil_streaming_csv": "",
        "unix_at_pupil_start": pd.NA,
        "synced_at_pupil_start": pd.NA,
        "pupil_duration_s": pd.NA,
        "pupil_recording_end_unix": pd.NA,
        "files_pupil_positions": pd.NA,
        "files_fixations": pd.NA,
        "files_blinks": pd.NA,
        "files_gaze_positions": pd.NA,
        "files_world_timestamps": pd.NA,
        "rtaps_session_id": "",
        "participant_id": "",
        "train_number": pd.NA,
        "session_start_unix": pd.NA,
        "session_end_unix": pd.NA,
        "n_steps": pd.NA,
        "match_overlap_s": pd.NA,
        "match_overlap_frac": pd.NA,
        "match_duration_ratio": pd.NA,
        "match_confidence": "UNMATCHED",
        "notes": "",
    }


def _populate_pupil(row: dict, rec: PupilRecording) -> None:
    row["source"] = "pupil_export"
    row["laptop"] = rec.laptop
    row["laptop_short"] = LAPTOP_SHORT.get(rec.laptop, rec.laptop.lower())
    row["user_dir"] = str(rec.user_dir)
    row["user_id"] = rec.user_id
    row["procedure_slug"] = rec.folder_procedure_slug
    row["pupil_export_dir"] = str(rec.user_dir)
    row["unix_at_pupil_start"] = rec.anchor.unix_at_pupil_start
    row["synced_at_pupil_start"] = rec.anchor.synced_at_pupil_start
    row["pupil_duration_s"] = rec.anchor.pupil_duration_s
    row["pupil_recording_end_unix"] = rec.anchor.unix_end
    for k, v in rec.files_present.items():
        row[f"files_{k}"] = v
    row["session_uid"] = session_uid(
        rec.laptop, rec.user_id, rec.folder_procedure_slug
    )


def _populate_rtaps(row: dict, m: RtapsMatch | None, slug: str) -> None:
    if m is None:
        return
    r = m.rtaps_row
    row["rtaps_session_id"] = str(r["sessionId"])
    row["participant_id"] = str(r["participantId"])
    row["train_number"] = int(r["parsed_train"]) if pd.notna(r["parsed_train"]) else pd.NA
    row["procedure_id"] = int(r["parsed_procedure_id"]) if pd.notna(r["parsed_procedure_id"]) else pd.NA
    row["session_start_unix"] = float(r["session_start_unix"])
    row["session_end_unix"] = float(r["session_end_unix"])
    row["n_steps"] = int(r["n_steps"])
    row["match_overlap_s"] = round(m.overlap_s, 2)
    row["match_overlap_frac"] = round(m.overlap_frac, 4)
    row["match_duration_ratio"] = round(m.duration_ratio, 3)
    row["match_confidence"] = m.confidence


def _populate_streaming(row: dict, s: StreamingCapture | None) -> None:
    if s is not None:
        row["pupil_streaming_csv"] = str(s.csv_path)


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--processed_root",
        type=Path,
        default=PROCESSED_ROOT,
        help=f"Output root (default: {PROCESSED_ROOT})",
    )
    args = ap.parse_args(argv)

    out_root: Path = args.processed_root
    out_root.mkdir(parents=True, exist_ok=True)

    print("[1/5] Parsing procedures.js …")
    proc_steps = parse_procedures_js(PROCEDURES_JS)
    proc_steps_path = out_root / "procedure_steps.csv"
    proc_steps.to_csv(proc_steps_path, index=False)
    print(
        f"      wrote {proc_steps_path} ({len(proc_steps)} rows across "
        f"{proc_steps['procedure_id'].nunique()} procedures)"
    )

    print("[2/5] Discovering Pupil Model_Data recordings …")
    recordings = discover_pupil_recordings()
    print(f"      found {len(recordings)} Pupil recordings")

    print("[3/5] Discovering Streaming pupil_data captures …")
    streams = discover_streaming_captures()
    print(f"      found {len(streams)} streaming captures")

    print(f"[4/5] Loading {RTAPS_SESSIONS_CSV.name} …")
    rtaps = load_rtaps_sessions(RTAPS_SESSIONS_CSV)
    print(f"      loaded {len(rtaps)} UI sessions")

    print("[5/5] Matching …")
    rows: list[dict] = []
    used_rtaps_ids: set[str] = set()
    used_streams: set[str] = set()

    # Pass 1: every Pupil recording gets a row
    for rec in recordings:
        row = _row_skeleton()
        _populate_pupil(row, rec)
        m = _match_rtaps_for_interval(
            procedure_slug=rec.folder_procedure_slug,
            start_unix=rec.anchor.unix_at_pupil_start,
            end_unix=rec.anchor.unix_end,
            duration_s=rec.anchor.pupil_duration_s,
            rtaps=rtaps,
            excluded_ids=used_rtaps_ids,
        )
        _populate_rtaps(row, m, rec.folder_procedure_slug)
        if m is not None:
            used_rtaps_ids.add(str(m.rtaps_row["sessionId"]))
        s_match = _match_streaming_for_pupil(rec, streams, used_streams)
        _populate_streaming(row, s_match)
        if s_match is not None:
            used_streams.add(str(s_match.csv_path))
        rows.append(row)

    # Pass 2: streaming captures with no Pupil export → standalone row
    for s in streams:
        if str(s.csv_path) in used_streams:
            continue
        row = _row_skeleton()
        row["source"] = "streaming_only"
        row["laptop"] = s.laptop
        row["laptop_short"] = LAPTOP_SHORT.get(s.laptop, s.laptop.lower())
        row["user_dir"] = ""
        row["user_id"] = s.s_id
        row["pupil_streaming_csv"] = str(s.csv_path)
        row["unix_at_pupil_start"] = s.filename_unix
        row["pupil_duration_s"] = pd.NA
        row["notes"] = (
            f"Streaming-only (no Model_Data export). Filename UTC "
            f"reconstructed from name; verify with first-sample timestamp."
        )
        # Try matching to any procedure_slug using a generous ±duration window
        for slug in ("centrifuge", "column_flushing", "pressure_testing"):
            m = _match_rtaps_for_interval(
                procedure_slug=slug,
                start_unix=s.filename_unix,
                end_unix=s.filename_unix + 1800,  # 30 min generous bound
                duration_s=1800.0,
                rtaps=rtaps,
                excluded_ids=used_rtaps_ids,
            )
            if m is not None and m.confidence != "low":
                row["procedure_slug"] = slug
                _populate_rtaps(row, m, slug)
                used_rtaps_ids.add(str(m.rtaps_row["sessionId"]))
                break
        if not row["session_uid"]:
            row["session_uid"] = (
                f"{LAPTOP_SHORT.get(s.laptop, s.laptop.lower())}__"
                f"S{s.s_id}T{s.t_id}__{row['procedure_slug'] or 'unknown'}"
            )
        rows.append(row)

    df = pd.DataFrame(rows)
    out_path = out_root / "session_index.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path} ({len(df)} rows)")

    _print_summary(df)
    _print_unmatched_rtaps(rtaps, used_rtaps_ids)

    return 0


def _print_summary(df: pd.DataFrame) -> None:
    print("\n=== session_index.csv summary ===")
    by_conf = df["match_confidence"].value_counts(dropna=False).to_dict()
    print(f"  match_confidence: {by_conf}")
    by_proc = (
        df.groupby(["procedure_slug", "match_confidence"], dropna=False)
        .size()
        .unstack(fill_value=0)
    )
    print("\n  rows per (procedure_slug × match_confidence):")
    print(by_proc.to_string().replace("\n", "\n    "))

    by_laptop = (
        df.groupby(["laptop_short", "source"], dropna=False)
        .size()
        .unstack(fill_value=0)
    )
    print("\n  rows per (laptop × source):")
    print(by_laptop.to_string().replace("\n", "\n    "))

    print("\n  rows needing manual review (UNMATCHED or low/medium):")
    mask = df["match_confidence"].isin(["UNMATCHED", "low", "medium"])
    cols = [
        "session_uid",
        "laptop_short",
        "user_dir",
        "procedure_slug",
        "match_confidence",
        "match_overlap_frac",
        "match_duration_ratio",
        "rtaps_session_id",
        "participant_id",
    ]
    sub = df.loc[mask, [c for c in cols if c in df.columns]].copy()
    if len(sub) == 0:
        print("    (none — all sessions matched cleanly)")
    else:
        for r in sub.to_dict(orient="records"):
            print(
                f"    [{r['match_confidence']:<10}] {r['session_uid']:<48} "
                f"overlap_frac={r['match_overlap_frac']} "
                f"dur_ratio={r['match_duration_ratio']} "
                f"-> rtaps={r['rtaps_session_id'] or 'NONE'} "
                f"participant={r['participant_id'] or 'NONE'}"
            )


def _print_unmatched_rtaps(rtaps: pd.DataFrame, used_rtaps_ids: set[str]) -> None:
    unmatched = rtaps[~rtaps["sessionId"].isin(used_rtaps_ids)]
    print(
        f"\n  RTAPS UI sessions not paired to any recording: {len(unmatched)} / {len(rtaps)}"
    )
    if len(unmatched) and len(unmatched) <= 25:
        for _, r in unmatched.iterrows():
            print(
                f"    {r['sessionId']:<28} {r['procedureName']:<32} "
                f"{r['participantId']:<6} totalTimeSec={r['totalTimeSec']}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
