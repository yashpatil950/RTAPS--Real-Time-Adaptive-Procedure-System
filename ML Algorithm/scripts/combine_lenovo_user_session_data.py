#!/usr/bin/env python3
"""
Combine fixation counts, pupil (diameter_3d only, both eyes), and blink data
from Pupil exports under Lenovo_laptop into one CSV per User_* session folder.

Default root: ML Algorithm/data/Lenovo_laptop (relative to repo).

Each session folder like Model_Data/User_223_Pressure_Testing/ gets:
  combined_session_export.csv

CSV rows use record_type:
  - SESSION_SUMMARY: aggregate counts + flags for left/right eye in pupil data
  - pupil: samples with valid diameter_3d (eye_id 0=right, 1=left)
  - blink: duration, start_timestamp, end_timestamp, confidence

Eye convention matches Pupil: eye_id 0 = right, 1 = left.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

USER_DIR_RE = re.compile(r"^User_\d+_", re.IGNORECASE)


def find_user_session_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_dir() and USER_DIR_RE.match(p.name))


def safe_read_csv(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"Warning: could not read {path}: {e}", file=sys.stderr)
        return None


def build_combined(session_dir: Path) -> pd.DataFrame:
    fix_df = safe_read_csv(session_dir / "fixations.csv")
    pup_df = safe_read_csv(session_dir / "pupil_positions.csv")
    blink_df = safe_read_csv(session_dir / "blinks.csv")

    fixation_count = len(fix_df) if fix_df is not None else 0
    blink_count = len(blink_df) if blink_df is not None else 0

    pupil_row_count = 0
    has_left = False
    has_right = False
    pupil_rows = pd.DataFrame()

    if pup_df is not None and not pup_df.empty and "diameter_3d" in pup_df.columns:
        p = pup_df.copy()
        p["diameter_3d"] = pd.to_numeric(p["diameter_3d"], errors="coerce")
        pupil_rows = p[p["diameter_3d"].notna()].copy()
        pupil_row_count = len(pupil_rows)
        if "eye_id" in pupil_rows.columns:
            eyes = set(pd.to_numeric(pupil_rows["eye_id"], errors="coerce").dropna().astype(int).unique())
            has_right = 0 in eyes
            has_left = 1 in eyes

    summary = pd.DataFrame(
        [
            {
                "record_type": "SESSION_SUMMARY",
                "session_folder": session_dir.name,
                "fixation_count": fixation_count,
                "blink_count": blink_count,
                "pupil_row_count": pupil_row_count,
                "has_left_eye": has_left,
                "has_right_eye": has_right,
                "pupil_timestamp": pd.NA,
                "world_index": pd.NA,
                "eye_id": pd.NA,
                "eye_label": pd.NA,
                "diameter_3d": pd.NA,
                "pupil_confidence": pd.NA,
                "norm_pos_x": pd.NA,
                "norm_pos_y": pd.NA,
                "pupil_method": pd.NA,
                "blink_id": pd.NA,
                "blink_start_timestamp": pd.NA,
                "blink_duration": pd.NA,
                "blink_end_timestamp": pd.NA,
                "blink_confidence": pd.NA,
            }
        ]
    )

    pieces: list[pd.DataFrame] = [summary]

    if not pupil_rows.empty:
        ts_col = "pupil_timestamp" if "pupil_timestamp" in pupil_rows.columns else (
            "timestamp" if "timestamp" in pupil_rows.columns else None
        )
        ts = pupil_rows[ts_col] if ts_col else pd.NA

        def eye_label(e):
            if pd.isna(e):
                return pd.NA
            return "left" if int(e) == 1 else "right" if int(e) == 0 else "unknown"

        labels = pupil_rows["eye_id"].map(eye_label) if "eye_id" in pupil_rows.columns else pd.NA

        pupil_out = pd.DataFrame(
            {
                "record_type": "pupil",
                "session_folder": session_dir.name,
                "fixation_count": pd.NA,
                "blink_count": pd.NA,
                "pupil_row_count": pd.NA,
                "has_left_eye": pd.NA,
                "has_right_eye": pd.NA,
                "pupil_timestamp": ts,
                "world_index": pupil_rows["world_index"] if "world_index" in pupil_rows.columns else pd.NA,
                "eye_id": pupil_rows["eye_id"] if "eye_id" in pupil_rows.columns else pd.NA,
                "eye_label": labels,
                "diameter_3d": pupil_rows["diameter_3d"],
                "pupil_confidence": pupil_rows["confidence"] if "confidence" in pupil_rows.columns else pd.NA,
                "norm_pos_x": pupil_rows["norm_pos_x"] if "norm_pos_x" in pupil_rows.columns else pd.NA,
                "norm_pos_y": pupil_rows["norm_pos_y"] if "norm_pos_y" in pupil_rows.columns else pd.NA,
                "pupil_method": pupil_rows["method"] if "method" in pupil_rows.columns else pd.NA,
                "blink_id": pd.NA,
                "blink_start_timestamp": pd.NA,
                "blink_duration": pd.NA,
                "blink_end_timestamp": pd.NA,
                "blink_confidence": pd.NA,
            }
        )
        pieces.append(pupil_out)

    if blink_df is not None and not blink_df.empty:
        blink_out = pd.DataFrame(
            {
                "record_type": "blink",
                "session_folder": session_dir.name,
                "fixation_count": pd.NA,
                "blink_count": pd.NA,
                "pupil_row_count": pd.NA,
                "has_left_eye": pd.NA,
                "has_right_eye": pd.NA,
                "pupil_timestamp": pd.NA,
                "world_index": pd.NA,
                "eye_id": pd.NA,
                "eye_label": pd.NA,
                "diameter_3d": pd.NA,
                "pupil_confidence": pd.NA,
                "norm_pos_x": pd.NA,
                "norm_pos_y": pd.NA,
                "pupil_method": pd.NA,
                "blink_id": blink_df["id"] if "id" in blink_df.columns else pd.NA,
                "blink_start_timestamp": blink_df["start_timestamp"]
                if "start_timestamp" in blink_df.columns
                else pd.NA,
                "blink_duration": blink_df["duration"] if "duration" in blink_df.columns else pd.NA,
                "blink_end_timestamp": blink_df["end_timestamp"]
                if "end_timestamp" in blink_df.columns
                else pd.NA,
                "blink_confidence": blink_df["confidence"] if "confidence" in blink_df.columns else pd.NA,
            }
        )
        pieces.append(blink_out)

    return pd.concat(pieces, ignore_index=True)


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    default_root = script_dir.parent / "data" / "Lenovo_laptop"

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help=f"Root folder containing User_* session dirs (default: {default_root})",
    )
    ap.add_argument(
        "--output-name",
        default="combined_session_export.csv",
        help="Output filename written inside each User_* folder",
    )
    ap.add_argument("--dry-run", action="store_true", help="List session folders only, do not write files")
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        sys.exit(f"Root is not a directory: {root}")

    sessions = find_user_session_dirs(root)
    if not sessions:
        sys.exit(f"No User_* session folders found under {root}")

    if args.dry_run:
        for s in sessions:
            print(s)
        print(f"Found {len(sessions)} session folder(s).")
        return

    written = 0
    for session_dir in sessions:
        out = build_combined(session_dir)
        out_path = session_dir / args.output_name
        out.to_csv(out_path, index=False)
        print(f"Wrote {out_path} ({len(out)} rows)")
        written += 1

    print(f"Done. Wrote {written} file(s).")


if __name__ == "__main__":
    main()
