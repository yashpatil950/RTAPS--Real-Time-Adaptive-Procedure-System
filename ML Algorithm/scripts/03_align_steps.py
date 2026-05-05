#!/usr/bin/env python3
"""Stage 3: convert UI step times to Pupil-clock intervals.

For each session in `session_index.csv` that has a matched RTAPS UI session
and a valid Pupil clock anchor, emit `step_boundaries.parquet` containing one
row per UI step with both UNIX and Pupil-`synced_s` timestamps, plus the
per-step `time_threshold_s` from `procedures.js`.

Output:
  _processed/<procedure_slug>/per_session/<session_uid>/step_boundaries.parquet
  _processed/step_alignment_summary.csv

Run:
  python "ML Algorithm/scripts/03_align_steps.py"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import PROCESSED_ROOT, RTAPS_SESSIONS_CSV  # noqa: E402
from lib.io_utils import load_rtaps_sessions  # noqa: E402
from lib.sync import ClockAnchor  # noqa: E402

STEP_OUT_COLS = [
    "session_uid",
    "rtaps_session_id",
    "step_number",
    "step_id",
    "start_unix_t",
    "end_unix_t",
    "start_synced_t",
    "end_synced_t",
    "duration_s",
    "threshold_s",
    "exceeded_threshold",
    "sub_steps_shown",
]


def _resolve_anchor(row: pd.Series) -> ClockAnchor | None:
    if pd.isna(row.get("unix_at_pupil_start")) or pd.isna(row.get("synced_at_pupil_start")):
        return None
    return ClockAnchor(
        unix_at_pupil_start=float(row["unix_at_pupil_start"]),
        synced_at_pupil_start=float(row["synced_at_pupil_start"]),
        pupil_duration_s=float(row.get("pupil_duration_s") or 0.0),
    )


def _build_step_boundaries(
    session_uid: str,
    rtaps_session_id: str,
    parsed_steps: list[dict],
    session_start_unix: float,
    anchor: ClockAnchor,
    threshold_lookup: dict[tuple[int, int], float],
    procedure_id: int | None,
) -> pd.DataFrame:
    rows: list[dict] = []
    cursor_unix = float(session_start_unix)
    for step in parsed_steps:
        try:
            step_number = int(step["stepNumber"])
            step_id = int(step["stepId"])
            duration_s = int(step.get("timeSpentSec", 0) or 0)
        except (KeyError, TypeError, ValueError):
            continue
        start_unix = cursor_unix
        end_unix = cursor_unix + duration_s
        cursor_unix = end_unix
        threshold = (
            threshold_lookup.get((procedure_id, step_id))
            if procedure_id is not None
            else None
        )
        rows.append(
            {
                "session_uid": session_uid,
                "rtaps_session_id": rtaps_session_id,
                "step_number": step_number,
                "step_id": step_id,
                "start_unix_t": start_unix,
                "end_unix_t": end_unix,
                "start_synced_t": anchor.unix_to_synced(start_unix),
                "end_synced_t": anchor.unix_to_synced(end_unix),
                "duration_s": duration_s,
                "threshold_s": float(threshold) if threshold is not None else float("nan"),
                "exceeded_threshold": bool(step.get("exceededThreshold", False)),
                "sub_steps_shown": bool(step.get("subStepsShown", False)),
            }
        )
    if not rows:
        return pd.DataFrame(columns=STEP_OUT_COLS)
    return pd.DataFrame(rows)[STEP_OUT_COLS]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed_root", type=Path, default=PROCESSED_ROOT)
    args = ap.parse_args(argv)

    sidx_path = args.processed_root / "session_index.csv"
    proc_path = args.processed_root / "procedure_steps.csv"
    if not sidx_path.is_file() or not proc_path.is_file():
        print("ERROR: run stages 01 (session index) and 01 (procedure_steps) first.")
        return 2

    sidx = pd.read_csv(sidx_path)
    proc_steps = pd.read_csv(proc_path)
    threshold_lookup = {
        (int(r["procedure_id"]), int(r["step_id"])): float(r["time_threshold_s"])
        for _, r in proc_steps.iterrows()
        if pd.notna(r.get("time_threshold_s"))
    }
    rtaps = load_rtaps_sessions(RTAPS_SESSIONS_CSV)
    rtaps_by_id = {str(r["sessionId"]): r for _, r in rtaps.iterrows()}

    summary_rows: list[dict] = []
    n_written = 0
    for _, row in sidx.iterrows():
        session_uid = str(row["session_uid"])
        slug = row.get("procedure_slug")
        rtaps_id = str(row.get("rtaps_session_id") or "").strip()
        if not slug or pd.isna(slug) or not rtaps_id:
            continue
        anchor = _resolve_anchor(row)
        if anchor is None:
            continue
        rtaps_row = rtaps_by_id.get(rtaps_id)
        if rtaps_row is None:
            continue

        parsed_steps = rtaps_row["parsed_steps"] or []
        proc_id = (
            int(rtaps_row["parsed_procedure_id"])
            if pd.notna(rtaps_row["parsed_procedure_id"])
            else None
        )
        sb = _build_step_boundaries(
            session_uid=session_uid,
            rtaps_session_id=rtaps_id,
            parsed_steps=parsed_steps,
            session_start_unix=float(rtaps_row["session_start_unix"]),
            anchor=anchor,
            threshold_lookup=threshold_lookup,
            procedure_id=proc_id,
        )
        if sb.empty:
            print(f"  ! {session_uid}: no parsed steps, skipping")
            continue

        out_dir = args.processed_root / slug / "per_session" / session_uid
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "step_boundaries.parquet"
        sb.to_parquet(out_path, index=False)
        n_written += 1

        # Diagnostics: how does the UI session start sit inside the Pupil recording?
        first_step_synced = float(sb["start_synced_t"].iloc[0])
        last_step_synced = float(sb["end_synced_t"].iloc[-1])
        offset_at_start = first_step_synced - anchor.synced_at_pupil_start
        offset_at_end = anchor.synced_end - last_step_synced
        ui_dur_s = float(sb["end_unix_t"].iloc[-1] - sb["start_unix_t"].iloc[0])

        summary_rows.append(
            {
                "session_uid": session_uid,
                "procedure_slug": slug,
                "n_steps": len(sb),
                "ui_duration_s": round(ui_dur_s, 1),
                "pupil_duration_s": round(anchor.pupil_duration_s, 1),
                "offset_pupil_to_first_step_s": round(offset_at_start, 1),
                "offset_last_step_to_pupil_end_s": round(offset_at_end, 1),
                "first_step_synced_t": round(first_step_synced, 3),
                "last_step_synced_t": round(last_step_synced, 3),
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_path = args.processed_root / "step_alignment_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"\nWrote {n_written} step_boundaries.parquet files")
    print(f"Wrote {summary_path}")
    _print_summary(summary_df)
    return 0


def _print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        print("\n  (no rows; nothing aligned)")
        return
    print("\n=== step_alignment_summary.csv ===")
    print(
        f"  median offset Pupil-start → first-step: "
        f"{df['offset_pupil_to_first_step_s'].median():.1f} s"
    )
    print(
        f"  median offset last-step → Pupil-end:   "
        f"{df['offset_last_step_to_pupil_end_s'].median():.1f} s"
    )
    print(f"  rows: {len(df)}")

    # Anything where the UI session sticks out past the Pupil recording is suspect
    weird = df[
        (df["offset_pupil_to_first_step_s"] < -30)
        | (df["offset_last_step_to_pupil_end_s"] < -30)
    ]
    if len(weird):
        print("\n  ! sessions where UI step interval extends >30 s outside the Pupil recording:")
        for _, r in weird.iterrows():
            print(
                f"    {r['session_uid']:<48} ui_dur={r['ui_duration_s']}s "
                f"pupil_dur={r['pupil_duration_s']}s  "
                f"start_off={r['offset_pupil_to_first_step_s']}s "
                f"end_off={r['offset_last_step_to_pupil_end_s']}s"
            )


if __name__ == "__main__":
    raise SystemExit(main())
