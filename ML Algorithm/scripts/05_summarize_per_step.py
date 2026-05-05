#!/usr/bin/env python3
"""Stage 5: per-step QA aggregation.

Reads `<procedure>/X_window.parquet`, groups by (session_uid, step_number),
and emits `<procedure>/X_step.parquet` with mean/std/median of every numeric
feature inside that step. Useful for sanity-checking within-step variance and
for any non-streaming baseline you want to try.

Run:
  python "ML Algorithm/scripts/05_summarize_per_step.py"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import PROCEDURE_ID_TO_SLUG, PROCESSED_ROOT  # noqa: E402

# Columns we don't aggregate (identifiers and labels).
KEY_COLS = [
    "session_uid",
    "procedure_slug",
    "procedure_id",
    "participant_id",
    "laptop_short",
    "rtaps_session_id",
    "step_number",
    "step_id",
]
PASSTHROUGH_COLS = [
    "step_threshold_s",
    "step_sub_steps_shown_eventually",
    "step_exceeded_threshold_eventually",
    "n_steps_remaining",
]
DROP_COLS = [
    "decision_time_synced_t",
    "decision_time_unix_t",
    "window_start_synced_t",
    "window_end_synced_t",
    "valid",
    "data_yield",
]


def _aggregate(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    grouped = df.groupby(["session_uid", "step_number"], dropna=False)
    rows: list[dict] = []
    for (session_uid, step_number), g in grouped:
        if pd.isna(step_number):
            continue
        first = g.iloc[0]
        out: dict = {
            "session_uid": session_uid,
            "step_number": int(step_number),
            "step_id": int(first["step_id"]) if pd.notna(first.get("step_id")) else pd.NA,
            "procedure_slug": first.get("procedure_slug"),
            "procedure_id": first.get("procedure_id"),
            "participant_id": first.get("participant_id"),
            "laptop_short": first.get("laptop_short"),
            "rtaps_session_id": first.get("rtaps_session_id"),
            "n_windows": len(g),
            "n_valid_windows": int(g["valid"].astype(bool).sum()) if "valid" in g.columns else len(g),
            "step_duration_observed_s": float(
                (g["decision_time_synced_t"].max() - g["decision_time_synced_t"].min())
                if "decision_time_synced_t" in g.columns and len(g) > 1
                else 0.0
            ),
        }
        for col in PASSTHROUGH_COLS:
            if col in g.columns:
                out[col] = first[col]

        feature_cols = [
            c
            for c in g.columns
            if c not in KEY_COLS + DROP_COLS + PASSTHROUGH_COLS + ["workload_label"]
        ]
        for c in feature_cols:
            s = pd.to_numeric(g[c], errors="coerce")
            if s.notna().sum() == 0:
                out[f"{c}__mean"] = float("nan")
                out[f"{c}__std"] = float("nan")
                out[f"{c}__median"] = float("nan")
                continue
            out[f"{c}__mean"] = float(s.mean(skipna=True))
            out[f"{c}__std"] = float(s.std(skipna=True, ddof=0)) if s.notna().sum() >= 2 else float("nan")
            out[f"{c}__median"] = float(s.median(skipna=True))

        if "workload_label" in g.columns:
            non_null = g["workload_label"].dropna()
            out["workload_label"] = non_null.iloc[0] if len(non_null) else pd.NA
        rows.append(out)

    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed_root", type=Path, default=PROCESSED_ROOT)
    args = ap.parse_args(argv)

    n_total = 0
    for slug in PROCEDURE_ID_TO_SLUG.values():
        in_path = args.processed_root / slug / "X_window.parquet"
        if not in_path.is_file():
            print(f"  ! {in_path} missing, skipping {slug}")
            continue
        df = pd.read_parquet(in_path)
        agg = _aggregate(df)
        out_path = args.processed_root / slug / "X_step.parquet"
        agg.to_parquet(out_path, index=False)
        n_total += len(agg)
        n_with_label = (
            int(agg["workload_label"].notna().sum()) if "workload_label" in agg.columns else 0
        )
        print(
            f"  wrote {out_path}: {len(agg)} steps × {agg.shape[1]} cols "
            f"(w/ label: {n_with_label})"
        )

    print(f"\nTotal per-step rows across all procedures: {n_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
