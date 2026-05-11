#!/usr/bin/env python3
"""Stage 4b: add normalized (z-scored) sensor features to X_window.parquet.

Phase 2 of the X→Y plan: compute z-scored variants of the 4 sensor features
plus pupil_diam_slope. Two normalization scopes:

  *_zp     : z-scored within each PARTICIPANT (across all their sessions)
              → removes individual differences in resting pupil size, blink rate,
                fixation duration, etc.

  *_zproc  : z-scored within each PROCEDURE
              → removes procedure-level laptop/lighting/camera confounds
                so the workload signal isn't masked by hardware differences.

Run AFTER stage 04 has written X_window.parquet for all procedures.

Reads:   _processed/<slug>/X_window.parquet
Writes:  _processed/<slug>/X_window.parquet (in-place, with new columns appended)

Run:
  python "ML Algorithm/scripts/04b_add_normalized_features.py"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import PROCEDURE_ID_TO_SLUG, PROCESSED_ROOT  # noqa: E402

# Features to z-score. Includes pupil_diam_slope which we'll bring back as a
# useful feature in Phase 3.
NORMALIZE_COLS = [
    "pupil_pcps_mean",
    "pupil_diam_slope",
    "blink_rate_30s",
    "fixation_dur_mean_ms",
    "fixation_dispersion_mean",
]


def _zscore_within(df: pd.DataFrame, group_col: str, cols: list[str], suffix: str) -> pd.DataFrame:
    """For each row, compute (x - group_mean) / group_std using only valid rows.

    NaN inputs stay NaN; rows in groups with std=0 or fewer than 5 valid values
    get NaN (insufficient data for stable z-score).
    """
    out = df.copy()
    for col in cols:
        if col not in df.columns:
            continue
        # Compute group-level mean and std using only the valid rows
        valid_df = df.loc[df["valid"].astype(bool) & df[col].notna(), [group_col, col]]
        stats = valid_df.groupby(group_col)[col].agg(["mean", "std", "count"]).rename(
            columns={"mean": "_m", "std": "_s", "count": "_n"}
        )
        # Map stats back to every row
        m = df[group_col].map(stats["_m"])
        s = df[group_col].map(stats["_s"])
        n = df[group_col].map(stats["_n"]).fillna(0)
        z = (df[col] - m) / s
        # Drop unstable z-scores (std==0 or insufficient data)
        unstable = (s == 0) | s.isna() | (n < 5)
        z = z.where(~unstable, np.nan)
        out[f"{col}_{suffix}"] = z.astype(float)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed_root", type=Path, default=PROCESSED_ROOT)
    args = ap.parse_args(argv)

    # Step 1: load all procedures' X_window.parquet, concatenate, remember origin
    frames: dict[str, pd.DataFrame] = {}
    for slug in PROCEDURE_ID_TO_SLUG.values():
        p = args.processed_root / slug / "X_window.parquet"
        if not p.is_file():
            print(f"  ! {p} missing — skipping {slug}")
            continue
        df = pd.read_parquet(p)
        frames[slug] = df
        print(f"  {slug}: {len(df)} windows loaded")
    if not frames:
        print("ERROR: no X_window.parquet files found; run stage 04 first.")
        return 2

    full = pd.concat(frames.values(), ignore_index=True)
    full["_origin_slug"] = pd.concat(
        [pd.Series([slug] * len(df)) for slug, df in frames.items()], ignore_index=True
    ).to_numpy()

    print(f"\nConcatenated {len(full)} windows across {len(frames)} procedures")

    # Step 2: per-participant z-scoring
    print("\nComputing per-participant z-scores (_zp)...")
    full = _zscore_within(full, "participant_id", NORMALIZE_COLS, "zp")

    # Step 3: per-procedure z-scoring
    print("Computing per-procedure z-scores (_zproc)...")
    full = _zscore_within(full, "_origin_slug", NORMALIZE_COLS, "zproc")

    # Step 4: print summary
    new_cols = [f"{c}_zp" for c in NORMALIZE_COLS] + [f"{c}_zproc" for c in NORMALIZE_COLS]
    print(f"\nAdded {len(new_cols)} new normalized columns:")
    for c in new_cols:
        if c in full.columns:
            valid = full[c].notna().sum()
            print(f"  {c}: {valid}/{len(full)} non-null  "
                  f"mean={full[c].mean():.3f}  std={full[c].std():.3f}")

    # Step 5: split back by procedure and overwrite parquets
    print("\nWriting updated parquets...")
    for slug in frames:
        sub = full[full["_origin_slug"] == slug].drop(columns=["_origin_slug"])
        out_path = args.processed_root / slug / "X_window.parquet"
        sub.to_parquet(out_path, index=False)
        print(f"  wrote {out_path}  ({len(sub)} rows, {len(sub.columns)} cols)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
