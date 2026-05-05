#!/usr/bin/env python3
"""Stage 2: per-session cleaned tidy parquets + per-session pupil baselines.

Reads `_processed/session_index.csv` from stage 1 and, for each session,
emits confidence-filtered parquets:

  _processed/<procedure_slug>/per_session/<session_uid>/
      pupil_clean.parquet         (synced_t, unix_t, eye_id, diameter_mm, confidence, source)
      fixations_clean.parquet     (start_synced_t, start_unix_t, duration_s, ...)
      blinks_clean.parquet        (start_synced_t, end_synced_t, duration_s, tracking_loss, ...)
      gaze_clean.parquet          (synced_t, unix_t, norm_pos_x, norm_pos_y, confidence)

Plus aggregate artifacts:
  _processed/baselines.csv        per-session pupil baseline (mean diameter in first 60 s)
  _processed/data_quality.csv     per-session sample counts, rates, yields, missing files

Pupil sample sourcing:
  - prefer offline export (`pupil_positions.csv`, pye3d only)
  - fall back to streaming CSV (`pupil_data_*.csv`, drop diameter == 0 placeholders)
  - if both missing, skip pupil cleaning but still try fixations/blinks/gaze

Run:
  python "ML Algorithm/scripts/02_clean_pupil_export.py"
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import (  # noqa: E402
    BASELINE_DURATION_S,
    BLINK_TRACKING_LOSS_S,
    MIN_CONFIDENCE,
    PROCESSED_ROOT,
)
from lib.sync import ClockAnchor  # noqa: E402

PUPIL_OUT_COLS = ["synced_t", "unix_t", "eye_id", "diameter_mm", "confidence", "source"]
FIX_OUT_COLS = [
    "fixation_id",
    "start_synced_t",
    "start_unix_t",
    "duration_s",
    "norm_pos_x",
    "norm_pos_y",
    "dispersion",
    "confidence",
]
BLINK_OUT_COLS = [
    "blink_id",
    "start_synced_t",
    "end_synced_t",
    "start_unix_t",
    "end_unix_t",
    "duration_s",
    "confidence",
    "tracking_loss",
]
GAZE_OUT_COLS = ["synced_t", "unix_t", "norm_pos_x", "norm_pos_y", "confidence"]


# --------------------------------------------------------------------------- #
# Pupil samples                                                               #
# --------------------------------------------------------------------------- #


def _read_pupil_offline(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(
            path,
            usecols=lambda c: c
            in {"pupil_timestamp", "eye_id", "confidence", "diameter_3d", "method"},
        )
    except Exception as e:
        print(f"      ! cannot read {path}: {e}")
        return None
    if "method" in df.columns:
        df = df[df["method"] == "pye3d 0.3.0 real-time"]
    if "diameter_3d" not in df.columns:
        return None
    df = df.dropna(subset=["diameter_3d"])
    df["diameter_3d"] = pd.to_numeric(df["diameter_3d"], errors="coerce")
    df = df.dropna(subset=["diameter_3d"])
    df = df[df["confidence"] >= MIN_CONFIDENCE]
    if df.empty:
        return None
    out = pd.DataFrame(
        {
            "synced_t": df["pupil_timestamp"].astype(float).to_numpy(),
            "eye_id": df["eye_id"].astype("int8").to_numpy(),
            "diameter_mm": df["diameter_3d"].astype(float).to_numpy(),
            "confidence": df["confidence"].astype(float).to_numpy(),
        }
    )
    out["source"] = "offline"
    return out


def _read_pupil_streaming(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path, usecols=["timestamp", "eye_id", "diameter", "confidence"])
    except Exception as e:
        print(f"      ! cannot read {path}: {e}")
        return None
    df["diameter"] = pd.to_numeric(df["diameter"], errors="coerce")
    df = df[df["diameter"] > 0]
    df = df[df["confidence"] >= MIN_CONFIDENCE]
    if df.empty:
        return None
    out = pd.DataFrame(
        {
            "synced_t": df["timestamp"].astype(float).to_numpy(),
            "eye_id": df["eye_id"].astype("int8").to_numpy(),
            "diameter_mm": df["diameter"].astype(float).to_numpy(),
            "confidence": df["confidence"].astype(float).to_numpy(),
        }
    )
    out["source"] = "streaming"
    return out


def _attach_unix(df: pd.DataFrame, anchor: ClockAnchor, t_col: str = "synced_t") -> pd.DataFrame:
    df = df.copy()
    df[f"{t_col[:-2]}unix_t" if t_col.endswith("_t") else f"{t_col}_unix"] = (
        df[t_col] - anchor.synced_at_pupil_start
    ) + anchor.unix_at_pupil_start
    return df


# --------------------------------------------------------------------------- #
# Fixations / blinks / gaze                                                   #
# --------------------------------------------------------------------------- #


def _clean_fixations(path: Path, anchor: ClockAnchor) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"      ! cannot read {path}: {e}")
        return None
    if df.empty:
        return None
    df = df.copy()
    df["duration_raw"] = pd.to_numeric(df["duration"], errors="coerce")
    # Pupil exports report fixation duration in milliseconds.
    df["duration_s"] = df["duration_raw"] / 1000.0
    out = pd.DataFrame(
        {
            "fixation_id": df.get("id", pd.Series(range(len(df)))).astype(int).to_numpy(),
            "start_synced_t": pd.to_numeric(df["start_timestamp"], errors="coerce")
            .astype(float)
            .to_numpy(),
            "duration_s": df["duration_s"].astype(float).to_numpy(),
            "norm_pos_x": pd.to_numeric(df.get("norm_pos_x", np.nan), errors="coerce")
            .astype(float)
            .to_numpy(),
            "norm_pos_y": pd.to_numeric(df.get("norm_pos_y", np.nan), errors="coerce")
            .astype(float)
            .to_numpy(),
            "dispersion": pd.to_numeric(df.get("dispersion", np.nan), errors="coerce")
            .astype(float)
            .to_numpy(),
            "confidence": pd.to_numeric(df.get("confidence", np.nan), errors="coerce")
            .astype(float)
            .to_numpy(),
        }
    )
    out["start_unix_t"] = (
        out["start_synced_t"] - anchor.synced_at_pupil_start
    ) + anchor.unix_at_pupil_start
    return out[FIX_OUT_COLS]


def _clean_blinks(path: Path, anchor: ClockAnchor) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"      ! cannot read {path}: {e}")
        return None
    if df.empty:
        return None
    df = df.copy()
    df["duration_s"] = pd.to_numeric(df["duration"], errors="coerce").astype(float)
    df["start_synced_t"] = pd.to_numeric(df["start_timestamp"], errors="coerce").astype(float)
    if "end_timestamp" in df.columns:
        df["end_synced_t"] = pd.to_numeric(df["end_timestamp"], errors="coerce").astype(float)
    else:
        df["end_synced_t"] = df["start_synced_t"] + df["duration_s"]
    out = pd.DataFrame(
        {
            "blink_id": df.get("id", pd.Series(range(len(df)))).astype(int).to_numpy(),
            "start_synced_t": df["start_synced_t"].to_numpy(),
            "end_synced_t": df["end_synced_t"].to_numpy(),
            "duration_s": df["duration_s"].to_numpy(),
            "confidence": pd.to_numeric(df.get("confidence", np.nan), errors="coerce")
            .astype(float)
            .to_numpy(),
        }
    )
    out["tracking_loss"] = out["duration_s"] >= BLINK_TRACKING_LOSS_S
    out["start_unix_t"] = (
        out["start_synced_t"] - anchor.synced_at_pupil_start
    ) + anchor.unix_at_pupil_start
    out["end_unix_t"] = (
        out["end_synced_t"] - anchor.synced_at_pupil_start
    ) + anchor.unix_at_pupil_start
    return out[BLINK_OUT_COLS]


def _clean_gaze(path: Path, anchor: ClockAnchor) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(
            path,
            usecols=lambda c: c in {"gaze_timestamp", "confidence", "norm_pos_x", "norm_pos_y"},
        )
    except Exception as e:
        print(f"      ! cannot read {path}: {e}")
        return None
    if df.empty:
        return None
    df = df.copy()
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
    df = df[df["confidence"] >= MIN_CONFIDENCE]
    if df.empty:
        return None
    out = pd.DataFrame(
        {
            "synced_t": pd.to_numeric(df["gaze_timestamp"], errors="coerce").astype(float).to_numpy(),
            "norm_pos_x": pd.to_numeric(df["norm_pos_x"], errors="coerce").astype(float).to_numpy(),
            "norm_pos_y": pd.to_numeric(df["norm_pos_y"], errors="coerce").astype(float).to_numpy(),
            "confidence": df["confidence"].astype(float).to_numpy(),
        }
    )
    out["unix_t"] = (out["synced_t"] - anchor.synced_at_pupil_start) + anchor.unix_at_pupil_start
    return out[GAZE_OUT_COLS]


# --------------------------------------------------------------------------- #
# Per-session orchestration                                                   #
# --------------------------------------------------------------------------- #


@dataclass
class CleanReport:
    session_uid: str = ""
    procedure_slug: str = ""
    pupil_source: str = ""
    pupil_n_rows: int = 0
    pupil_n_eye0: int = 0
    pupil_n_eye1: int = 0
    pupil_rate_hz_eye0: float = 0.0
    pupil_rate_hz_eye1: float = 0.0
    pupil_baseline_mm_eye0: float = float("nan")
    pupil_baseline_mm_eye1: float = float("nan")
    pupil_baseline_mm_mean: float = float("nan")
    fixations_n: int = 0
    blinks_n: int = 0
    blinks_n_tracking_loss: int = 0
    gaze_n: int = 0
    notes: list[str] = field(default_factory=list)


def _resolve_anchor(row: pd.Series) -> ClockAnchor | None:
    if pd.isna(row.get("unix_at_pupil_start")) or pd.isna(row.get("synced_at_pupil_start")):
        return None
    return ClockAnchor(
        unix_at_pupil_start=float(row["unix_at_pupil_start"]),
        synced_at_pupil_start=float(row["synced_at_pupil_start"]),
        pupil_duration_s=float(row.get("pupil_duration_s") or 0.0),
    )


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _compute_baseline(pupil: pd.DataFrame, anchor: ClockAnchor) -> tuple[float, float]:
    """Return (baseline_eye0_mm, baseline_eye1_mm) from the first BASELINE_DURATION_S."""
    if pupil.empty:
        return float("nan"), float("nan")
    cutoff = anchor.synced_at_pupil_start + BASELINE_DURATION_S
    early = pupil[pupil["synced_t"] <= cutoff]
    if early.empty:
        return float("nan"), float("nan")
    e0 = early[early["eye_id"] == 0]["diameter_mm"]
    e1 = early[early["eye_id"] == 1]["diameter_mm"]
    return (
        float(e0.mean()) if len(e0) else float("nan"),
        float(e1.mean()) if len(e1) else float("nan"),
    )


def _resolve_pupil(row: pd.Series, anchor: ClockAnchor | None) -> tuple[pd.DataFrame | None, str]:
    """Pick offline export if usable; otherwise fall back to streaming."""
    pupil_path = None
    if (
        row.get("pupil_export_dir")
        and row.get("files_pupil_positions") in (True, "True", "true")
    ):
        pupil_path = Path(str(row["pupil_export_dir"])) / "pupil_positions.csv"
        if pupil_path.is_file():
            df = _read_pupil_offline(pupil_path)
            if df is not None and not df.empty:
                return df, "offline"
    streaming = row.get("pupil_streaming_csv")
    if isinstance(streaming, str) and streaming and Path(streaming).is_file():
        df = _read_pupil_streaming(Path(streaming))
        if df is not None and not df.empty:
            if anchor is None:
                # streaming-only session: anchor = first sample
                df = df.sort_values("synced_t")
                # we leave caller to update the anchor
            return df, "streaming"
    return None, ""


def _process_session(row: pd.Series, processed_root: Path) -> CleanReport:
    rep = CleanReport(
        session_uid=row["session_uid"], procedure_slug=row.get("procedure_slug") or "unknown"
    )
    if rep.procedure_slug in (None, "", "unknown") or pd.isna(rep.procedure_slug):
        rep.notes.append("skipped: no procedure_slug (UNMATCHED row)")
        return rep

    anchor = _resolve_anchor(row)
    if anchor is None:
        # streaming-only path: anchor will come from filename + first sample
        if not (
            isinstance(row.get("pupil_streaming_csv"), str) and row["pupil_streaming_csv"]
        ):
            rep.notes.append("skipped: no anchor and no streaming csv")
            return rep
        # We need a tentative anchor to compute unix_t. Use filename UTC + first synced.
        # The session_index has unix_at_pupil_start (filename UTC) for streaming-only rows.
        df_stream = _read_pupil_streaming(Path(row["pupil_streaming_csv"]))
        if df_stream is None or df_stream.empty:
            rep.notes.append("skipped: streaming csv unreadable")
            return rep
        anchor = ClockAnchor(
            unix_at_pupil_start=float(row["unix_at_pupil_start"]),
            synced_at_pupil_start=float(df_stream["synced_t"].min()),
            pupil_duration_s=float(df_stream["synced_t"].max() - df_stream["synced_t"].min()),
        )
        del df_stream

    out_dir = processed_root / rep.procedure_slug / "per_session" / rep.session_uid

    pupil, source = _resolve_pupil(row, anchor)
    if pupil is not None:
        pupil = pupil.sort_values("synced_t").reset_index(drop=True)
        pupil["unix_t"] = (pupil["synced_t"] - anchor.synced_at_pupil_start) + anchor.unix_at_pupil_start
        pupil = pupil[PUPIL_OUT_COLS]
        _write_parquet(out_dir / "pupil_clean.parquet", pupil)
        rep.pupil_source = source
        rep.pupil_n_rows = len(pupil)
        for eid in (0, 1):
            sub = pupil[pupil["eye_id"] == eid]
            n = len(sub)
            setattr(rep, f"pupil_n_eye{eid}", n)
            if n >= 2:
                dur = float(sub["synced_t"].max() - sub["synced_t"].min())
                setattr(rep, f"pupil_rate_hz_eye{eid}", round(n / dur, 2) if dur > 0 else 0.0)
        b0, b1 = _compute_baseline(pupil, anchor)
        rep.pupil_baseline_mm_eye0 = b0
        rep.pupil_baseline_mm_eye1 = b1
        if not (np.isnan(b0) and np.isnan(b1)):
            rep.pupil_baseline_mm_mean = float(np.nanmean([b0, b1]))
    else:
        rep.notes.append("no usable pupil source")

    if row.get("pupil_export_dir") and row.get("files_fixations") in (True, "True", "true"):
        fix_path = Path(str(row["pupil_export_dir"])) / "fixations.csv"
        if fix_path.is_file():
            fix = _clean_fixations(fix_path, anchor)
            if fix is not None and not fix.empty:
                _write_parquet(out_dir / "fixations_clean.parquet", fix)
                rep.fixations_n = len(fix)

    if row.get("pupil_export_dir") and row.get("files_blinks") in (True, "True", "true"):
        bl_path = Path(str(row["pupil_export_dir"])) / "blinks.csv"
        if bl_path.is_file():
            bl = _clean_blinks(bl_path, anchor)
            if bl is not None and not bl.empty:
                _write_parquet(out_dir / "blinks_clean.parquet", bl)
                rep.blinks_n = len(bl)
                rep.blinks_n_tracking_loss = int(bl["tracking_loss"].sum())

    if row.get("pupil_export_dir") and row.get("files_gaze_positions") in (True, "True", "true"):
        gz_path = Path(str(row["pupil_export_dir"])) / "gaze_positions.csv"
        if gz_path.is_file():
            gz = _clean_gaze(gz_path, anchor)
            if gz is not None and not gz.empty:
                _write_parquet(out_dir / "gaze_clean.parquet", gz)
                rep.gaze_n = len(gz)

    return rep


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

    sidx_path = args.processed_root / "session_index.csv"
    if not sidx_path.is_file():
        print(f"ERROR: {sidx_path} not found. Run 01_build_session_index.py first.")
        return 2

    sidx = pd.read_csv(sidx_path)
    print(f"Loaded {len(sidx)} sessions from {sidx_path.name}")

    reports: list[CleanReport] = []
    for i, row in sidx.iterrows():
        print(f"[{i + 1}/{len(sidx)}] {row['session_uid']}")
        rep = _process_session(row, args.processed_root)
        reports.append(rep)
        notes = "; ".join(rep.notes) if rep.notes else ""
        print(
            f"      pupil={rep.pupil_n_rows} (src={rep.pupil_source or '-'}, "
            f"~{rep.pupil_rate_hz_eye0:.0f}/{rep.pupil_rate_hz_eye1:.0f} Hz/eye) "
            f"fix={rep.fixations_n} blinks={rep.blinks_n} (loss={rep.blinks_n_tracking_loss}) "
            f"gaze={rep.gaze_n}"
            + (f"  [{notes}]" if notes else "")
        )

    dq = pd.DataFrame([r.__dict__ for r in reports])
    dq["notes"] = dq["notes"].apply(lambda v: "; ".join(v) if isinstance(v, list) else v)
    dq_path = args.processed_root / "data_quality.csv"
    dq.to_csv(dq_path, index=False)

    bl = dq[
        ["session_uid", "procedure_slug", "pupil_baseline_mm_eye0",
         "pupil_baseline_mm_eye1", "pupil_baseline_mm_mean"]
    ].copy()
    bl_path = args.processed_root / "baselines.csv"
    bl.to_csv(bl_path, index=False)

    print(f"\nWrote {dq_path}")
    print(f"Wrote {bl_path}")
    _print_dq_summary(dq)
    return 0


def _print_dq_summary(dq: pd.DataFrame) -> None:
    print("\n=== data_quality.csv summary ===")
    have_pupil = (dq["pupil_n_rows"] > 0).sum()
    have_fix = (dq["fixations_n"] > 0).sum()
    have_blinks = (dq["blinks_n"] > 0).sum()
    have_gaze = (dq["gaze_n"] > 0).sum()
    print(
        f"  sessions with pupil={have_pupil}/{len(dq)}, fixations={have_fix}/{len(dq)}, "
        f"blinks={have_blinks}/{len(dq)}, gaze={have_gaze}/{len(dq)}"
    )

    by_proc = dq.groupby("procedure_slug").agg(
        n=("session_uid", "count"),
        with_pupil=("pupil_n_rows", lambda s: int((s > 0).sum())),
        with_fix=("fixations_n", lambda s: int((s > 0).sum())),
        with_blinks=("blinks_n", lambda s: int((s > 0).sum())),
        with_gaze=("gaze_n", lambda s: int((s > 0).sum())),
    )
    print("\n  per procedure:")
    print(by_proc.to_string().replace("\n", "\n    "))

    flagged = dq[
        (dq["pupil_n_rows"] > 0)
        & ((dq["pupil_rate_hz_eye0"] < 30) & (dq["pupil_rate_hz_eye1"] < 30))
    ]
    if len(flagged):
        print("\n  ! sessions with low pupil sample rate (<30 Hz both eyes):")
        for _, r in flagged.iterrows():
            print(
                f"    {r['session_uid']}: eye0={r['pupil_rate_hz_eye0']:.0f}Hz "
                f"eye1={r['pupil_rate_hz_eye1']:.0f}Hz"
            )

    no_data = dq[(dq["pupil_n_rows"] == 0) & (dq["fixations_n"] == 0)]
    if len(no_data):
        print("\n  ! sessions with no pupil AND no fixations (cannot featurize):")
        for _, r in no_data.iterrows():
            print(f"    {r['session_uid']}: {r['notes']}")


if __name__ == "__main__":
    raise SystemExit(main())
