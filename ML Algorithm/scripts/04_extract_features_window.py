#!/usr/bin/env python3
"""Stage 4: extract per-window features into `<procedure>/X_window.parquet`.

For every session that has both a clock anchor and step_boundaries, we walk a
1-second decision grid inside the procedure, build a causal window
[t - WINDOW_LEN_S, t], and emit one row of features.

Outputs:
  _processed/<procedure_slug>/X_window.parquet      primary training X
  _processed/<procedure_slug>/X_window_sample.csv   5% stratified sample (eyeballable)
  _processed/feature_dictionary.md                   one row per feature (formula, units, source, deploy_feasible)
  _processed/X_window_summary.csv                    per-session row counts and yields

Run:
  python "ML Algorithm/scripts/04_extract_features_window.py"
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import (  # noqa: E402
    blink_features,
    fixation_features,
    gaze_features,
    pupil_features,
    task_features,
)
from lib.config import (  # noqa: E402
    BLINK_LONG_THRESH_S,
    GAZE_GRID,
    MIN_DATA_YIELD,
    PROCESSED_ROOT,
    PROCEDURE_ID_TO_SLUG,
    PROCEDURE_SLUG_TO_ID,
    STRIDE_S,
    WINDOW_LEN_S,
)
from lib.sync import ClockAnchor  # noqa: E402

EXPECTED_PUPIL_RATE_HZ = 60.0  # per eye

PRIMARY_KEY_COLS = [
    "session_uid",
    "procedure_slug",
    "procedure_id",
    "participant_id",
    "laptop_short",
    "rtaps_session_id",
    "decision_time_synced_t",
    "decision_time_unix_t",
    "window_start_synced_t",
    "window_end_synced_t",
]

QC_COLS = ["valid", "data_yield"]


# --------------------------------------------------------------------------- #
# I/O helpers                                                                 #
# --------------------------------------------------------------------------- #


def _safe_read_parquet(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as e:
        print(f"  ! failed reading {path}: {e}")
        return None


@dataclass
class SessionData:
    session_uid: str
    procedure_slug: str
    procedure_id: int
    participant_id: str
    laptop_short: str
    rtaps_session_id: str
    anchor: ClockAnchor
    baseline: pupil_features.PupilBaseline
    pupil: pd.DataFrame | None
    fixations: pd.DataFrame | None
    blinks: pd.DataFrame | None
    gaze: pd.DataFrame | None
    step_boundaries: pd.DataFrame


def _resolve_anchor(row: pd.Series) -> ClockAnchor | None:
    if pd.isna(row.get("unix_at_pupil_start")) or pd.isna(row.get("synced_at_pupil_start")):
        return None
    return ClockAnchor(
        unix_at_pupil_start=float(row["unix_at_pupil_start"]),
        synced_at_pupil_start=float(row["synced_at_pupil_start"]),
        pupil_duration_s=float(row.get("pupil_duration_s") or 0.0),
    )


def _load_session(
    sidx_row: pd.Series, baselines_row: pd.Series, processed_root: Path
) -> SessionData | None:
    slug = sidx_row.get("procedure_slug")
    if not slug or pd.isna(slug):
        return None
    anchor = _resolve_anchor(sidx_row)
    if anchor is None:
        return None
    session_uid = str(sidx_row["session_uid"])
    base_dir = processed_root / slug / "per_session" / session_uid
    sb_path = base_dir / "step_boundaries.parquet"
    if not sb_path.is_file():
        return None
    step_boundaries = pd.read_parquet(sb_path)
    if step_boundaries.empty:
        return None
    procedure_id = (
        int(sidx_row["procedure_id"])
        if pd.notna(sidx_row.get("procedure_id"))
        else PROCEDURE_SLUG_TO_ID.get(slug, -1)
    )
    return SessionData(
        session_uid=session_uid,
        procedure_slug=slug,
        procedure_id=procedure_id,
        participant_id=str(sidx_row.get("participant_id") or ""),
        laptop_short=str(sidx_row.get("laptop_short") or ""),
        rtaps_session_id=str(sidx_row.get("rtaps_session_id") or ""),
        anchor=anchor,
        baseline=pupil_features.PupilBaseline.from_row(baselines_row),
        pupil=_safe_read_parquet(base_dir / "pupil_clean.parquet"),
        fixations=_safe_read_parquet(base_dir / "fixations_clean.parquet"),
        blinks=_safe_read_parquet(base_dir / "blinks_clean.parquet"),
        gaze=_safe_read_parquet(base_dir / "gaze_clean.parquet"),
        step_boundaries=step_boundaries.sort_values("step_number").reset_index(drop=True),
    )


# --------------------------------------------------------------------------- #
# Per-session featurization                                                   #
# --------------------------------------------------------------------------- #


def _featurize_session(sd: SessionData) -> pd.DataFrame:
    sb = sd.step_boundaries
    n_steps_total = len(sb)
    session_start = float(sb["start_synced_t"].iloc[0])
    session_end = float(sb["end_synced_t"].iloc[-1])
    pupil_start = sd.anchor.synced_at_pupil_start
    pupil_end = sd.anchor.synced_end

    # decision grid: every STRIDE seconds inside the procedure, plus one full
    # window of warmup at the start.
    t_first = max(session_start + WINDOW_LEN_S, pupil_start + WINDOW_LEN_S)
    t_last = min(session_end, pupil_end)
    if t_last <= t_first:
        return pd.DataFrame()
    t_grid = np.arange(t_first, t_last + STRIDE_S * 0.5, STRIDE_S)
    if len(t_grid) == 0:
        return pd.DataFrame()

    step_starts = sb["start_synced_t"].to_numpy(dtype=float)
    step_ends = sb["end_synced_t"].to_numpy(dtype=float)

    # Pre-sort once per source. Grab numpy arrays for fast searchsorted.
    pupil_t = (
        sd.pupil["synced_t"].to_numpy(dtype=float) if sd.pupil is not None and len(sd.pupil) else None
    )
    fix_t = (
        sd.fixations["start_synced_t"].to_numpy(dtype=float)
        if sd.fixations is not None and len(sd.fixations)
        else None
    )
    blink_starts = (
        sd.blinks["start_synced_t"].to_numpy(dtype=float)
        if sd.blinks is not None and len(sd.blinks)
        else None
    )
    gaze_t = (
        sd.gaze["synced_t"].to_numpy(dtype=float) if sd.gaze is not None and len(sd.gaze) else None
    )

    # Pre-mask the blinks dataframe for cumulative counts
    if sd.blinks is not None and len(sd.blinks):
        not_loss = ~sd.blinks["tracking_loss"].astype(bool).to_numpy()
        long_mask = (
            sd.blinks["duration_s"].to_numpy(dtype=float) >= BLINK_LONG_THRESH_S
        ) & not_loss
        valid_starts = sd.blinks["start_synced_t"].to_numpy(dtype=float)
        cum_starts = np.sort(valid_starts[not_loss])
        cum_long_starts = np.sort(valid_starts[long_mask])
    else:
        cum_starts = np.array([])
        cum_long_starts = np.array([])

    rows: list[dict] = []
    for t in t_grid:
        w_lo = t - WINDOW_LEN_S
        w_hi = t

        # Step lookup: latest step whose start_synced_t <= t
        step_idx = int(np.searchsorted(step_starts, t, side="right") - 1)
        if step_idx < 0 or step_idx >= n_steps_total:
            continue
        # If t is past the last step's end, attribute to the last step
        # (operator finished the procedure but Pupil kept recording).
        # We skip those windows because they are no longer "in a step".
        if t > step_ends[step_idx]:
            continue
        step_row = sb.iloc[step_idx]

        feat: dict = {
            "session_uid": sd.session_uid,
            "procedure_slug": sd.procedure_slug,
            "procedure_id": sd.procedure_id,
            "participant_id": sd.participant_id,
            "laptop_short": sd.laptop_short,
            "rtaps_session_id": sd.rtaps_session_id,
            "decision_time_synced_t": float(t),
            "decision_time_unix_t": sd.anchor.synced_to_unix(float(t)),
            "window_start_synced_t": float(w_lo),
            "window_end_synced_t": float(w_hi),
        }

        # Pupil window slice
        if pupil_t is not None:
            i_lo = int(np.searchsorted(pupil_t, w_lo, side="left"))
            i_hi = int(np.searchsorted(pupil_t, w_hi, side="right"))
            sub = sd.pupil.iloc[i_lo:i_hi]
            feat.update(
                pupil_features.extract(
                    sub,
                    window_len_s=WINDOW_LEN_S,
                    expected_rate_hz_per_eye=EXPECTED_PUPIL_RATE_HZ,
                    baseline=sd.baseline,
                )
            )
        else:
            feat.update({k: float("nan") for k in pupil_features.PUPIL_FEATURE_NAMES})

        # Fixations
        if fix_t is not None:
            i_lo = int(np.searchsorted(fix_t, w_lo, side="left"))
            i_hi = int(np.searchsorted(fix_t, w_hi, side="right"))
            sub_f = sd.fixations.iloc[i_lo:i_hi]
            feat.update(fixation_features.extract(sub_f, window_len_s=WINDOW_LEN_S))
        else:
            feat.update({k: float("nan") for k in fixation_features.FIXATION_FEATURE_NAMES})
            sub_f = pd.DataFrame()

        # Blinks
        if blink_starts is not None:
            i_lo = int(np.searchsorted(blink_starts, w_lo, side="left"))
            i_hi = int(np.searchsorted(blink_starts, w_hi, side="right"))
            sub_b = sd.blinks.iloc[i_lo:i_hi]
            feat.update(
                blink_features.extract(
                    sub_b, window_len_s=WINDOW_LEN_S, long_thresh_s=BLINK_LONG_THRESH_S
                )
            )
        else:
            feat.update({k: float("nan") for k in blink_features.BLINK_FEATURE_NAMES})

        # Gaze
        sub_g = None
        if gaze_t is not None:
            i_lo = int(np.searchsorted(gaze_t, w_lo, side="left"))
            i_hi = int(np.searchsorted(gaze_t, w_hi, side="right"))
            sub_g = sd.gaze.iloc[i_lo:i_hi]
        feat.update(
            gaze_features.extract(
                sub_g,
                fix_window=sub_f if len(sub_f) else None,
                window_len_s=WINDOW_LEN_S,
                grid=GAZE_GRID,
            )
        )

        # Cumulative session counters (causal)
        cum_blink_count = int(np.searchsorted(cum_starts, t, side="right")) if len(cum_starts) else 0
        cum_long_count = (
            int(np.searchsorted(cum_long_starts, t, side="right")) if len(cum_long_starts) else 0
        )

        # Task / running context
        feat.update(
            task_features.extract_task(
                decision_t=float(t),
                window_start=float(w_lo),
                window_len_s=WINDOW_LEN_S,
                step_row=step_row,
                n_steps_total=n_steps_total,
                session_start_synced=session_start,
                cum_blink_count=cum_blink_count,
                cum_long_blink_count=cum_long_count,
            )
        )

        # QC
        py = feat.get("pupil_data_yield", float("nan"))
        fc = feat.get("fixation_count", 0.0)
        feat["data_yield"] = py
        feat["valid"] = bool(
            (not np.isnan(py) and py >= MIN_DATA_YIELD)
            or (not np.isnan(fc) and fc >= 1.0)
        )

        # Workload label placeholder — filled at join time below.
        feat["workload_label"] = pd.NA

        rows.append(feat)

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Feature dictionary                                                          #
# --------------------------------------------------------------------------- #


def _write_feature_dictionary(out_path: Path) -> None:
    rows: list[tuple[str, str, str, str, str, str]] = []

    def add(name: str, formula: str, units: str, source: str, deploy: str, notes: str = ""):
        rows.append((name, formula, units, source, deploy, notes))

    # Identifiers / QC
    for name in PRIMARY_KEY_COLS + ["data_yield", "valid", "workload_label"]:
        add(name, "key/QC", "-", "stage 1-3 join", "yes", "non-feature")

    # Pupil
    add("pupil_n_samples", "count(samples) in window", "n", "pupil_clean", "yes")
    add(
        "pupil_data_yield",
        "n_samples / (window_len_s * 60 Hz/eye * 2)",
        "ratio",
        "pupil_clean",
        "yes",
    )
    add("pupil_diam_mean", "mean(diameter_mm)", "mm", "pupil_clean", "yes")
    add("pupil_diam_std", "std(diameter_mm)", "mm", "pupil_clean", "yes")
    add("pupil_diam_median", "median(diameter_mm)", "mm", "pupil_clean", "yes")
    add("pupil_diam_iqr", "Q3 - Q1 of diameter_mm", "mm", "pupil_clean", "yes")
    add(
        "pupil_diam_slope",
        "linear regression slope of diameter on synced_t",
        "mm/s",
        "pupil_clean",
        "yes",
    )
    add("pupil_diam_range", "max - min", "mm", "pupil_clean", "yes")
    add(
        "pupil_eye_asymmetry",
        "|mean(eye0) - mean(eye1)|",
        "mm",
        "pupil_clean",
        "yes",
    )
    add(
        "pupil_pcps_mean",
        "mean((d - baseline_eye_mm) / baseline_eye_mm), per eye then concat",
        "ratio",
        "pupil_clean + baselines.csv",
        "yes",
        "PCPS = % change in pupil size; needs participant baseline",
    )
    add("pupil_pcps_std", "std(PCPS samples)", "ratio", "pupil_clean + baselines", "yes")
    add(
        "pupil_diam_mean_z",
        "(diam_mean - baseline_mean_mm) / baseline_mean_mm",
        "ratio",
        "pupil_clean + baselines",
        "yes",
    )
    add(
        "pupil_diam_slope_z",
        "diam_slope / baseline_mean_mm",
        "1/s",
        "pupil_clean + baselines",
        "yes",
    )

    # Blinks
    add("blink_count", "count of non-tracking-loss blinks in window", "n", "blinks_clean", "yes")
    add(
        "blink_rate_per_min",
        "blink_count * 60 / window_len_s",
        "/min",
        "blinks_clean",
        "yes",
    )
    add("blink_dur_mean_s", "mean(duration_s)", "s", "blinks_clean", "yes")
    add("blink_dur_std_s", "std(duration_s)", "s", "blinks_clean", "yes")
    add(
        "blink_inter_interval_mean_s",
        "mean of diff(start_synced_t) for blinks in window",
        "s",
        "blinks_clean",
        "yes",
    )
    add("blink_inter_interval_cv", "std / mean of inter-blink intervals", "ratio", "blinks_clean", "yes")
    add(
        "blink_long_count",
        f"count(blinks where duration_s >= {BLINK_LONG_THRESH_S}s)",
        "n",
        "blinks_clean",
        "yes",
    )

    # Fixations
    add("fixation_count", "count of fixations starting in window", "n", "fixations_clean", "yes")
    add("fixation_rate_per_sec", "fixation_count / window_len_s", "/s", "fixations_clean", "yes")
    add("fixation_dur_mean_ms", "mean(duration_s) * 1000", "ms", "fixations_clean", "yes")
    add("fixation_dur_std_ms", "std(duration_s) * 1000", "ms", "fixations_clean", "yes")
    add("fixation_dur_median_ms", "median(duration_s) * 1000", "ms", "fixations_clean", "yes")
    add("fixation_dispersion_mean", "mean(dispersion)", "deg", "fixations_clean", "yes")
    add("fixation_dispersion_std", "std(dispersion)", "deg", "fixations_clean", "yes")
    add(
        "fixation_time_in_fixation_ratio",
        "sum(duration_s) / window_len_s",
        "ratio",
        "fixations_clean",
        "yes",
    )
    add(
        "fixation_saccade_amp_mean",
        "mean Euclidean delta between consecutive fixation centroids",
        "norm",
        "fixations_clean",
        "yes",
        "proxy for saccade amplitude",
    )

    # Gaze
    add("gaze_n_samples", "count(samples) in window", "n", "gaze_clean", "yes")
    add("gaze_norm_x_mean", "mean(norm_pos_x)", "norm", "gaze_clean / fixations fallback", "yes")
    add("gaze_norm_y_mean", "mean(norm_pos_y)", "norm", "gaze_clean / fixations fallback", "yes")
    add("gaze_norm_x_std", "std(norm_pos_x)", "norm", "gaze_clean / fixations fallback", "yes")
    add("gaze_norm_y_std", "std(norm_pos_y)", "norm", "gaze_clean / fixations fallback", "yes")
    add(
        "gaze_region_entropy",
        f"Shannon entropy over {GAZE_GRID[0]}x{GAZE_GRID[1]} grid of norm_pos",
        "bits",
        "gaze_clean / fixations fallback",
        "yes",
    )
    add(
        "gaze_region_top1_ratio",
        "max(p_cell)",
        "ratio",
        "gaze_clean / fixations fallback",
        "yes",
    )
    add(
        "gaze_transitions_per_sec",
        "count(diff(cell_id) != 0) / window_len_s",
        "/s",
        "gaze_clean / fixations fallback",
        "yes",
    )

    # Task / running context
    add("step_number", "from rtaps_sessions step list", "ordinal", "step_boundaries", "yes")
    add("step_id", "from rtaps_sessions step list", "id", "step_boundaries", "yes")
    add("n_steps_remaining", "n_steps_total - step_number", "n", "step_boundaries", "yes")
    add("step_threshold_s", "from procedures.js timeThreshold", "s", "procedure_steps", "yes")
    add(
        "time_in_step_so_far_s",
        "decision_t - step_start_synced_t",
        "s",
        "step_boundaries",
        "yes",
    )
    add(
        "is_over_threshold_now",
        "1 if time_in_step_so_far_s > step_threshold_s",
        "0/1",
        "derived",
        "yes",
    )
    add(
        "progress_vs_threshold",
        f"min(time_in_step_so_far_s / step_threshold_s, {task_features.PROGRESS_CAP})",
        "ratio",
        "derived",
        "yes",
    )
    add(
        "step_sub_steps_shown_eventually",
        "step.subStepsShown from rtaps_sessions (END-OF-STEP value)",
        "0/1",
        "step_boundaries",
        "no — leaky",
        "Use only as outcome / oracle proxy. Live system would have a running 'shown_so_far' bool.",
    )
    add(
        "step_exceeded_threshold_eventually",
        "step.exceededThreshold from rtaps_sessions (END-OF-STEP)",
        "0/1",
        "step_boundaries",
        "no — leaky",
        "Use only as outcome / oracle proxy.",
    )
    add(
        "cumulative_session_time_s",
        "decision_t - first_step_start_synced_t",
        "s",
        "derived",
        "yes",
    )
    add(
        "cumulative_blink_count_session",
        "count of non-loss blinks with start_synced_t <= decision_t",
        "n",
        "blinks_clean",
        "yes",
    )
    add(
        "cumulative_long_blink_count_session",
        f"count of blinks with duration_s >= {BLINK_LONG_THRESH_S} s and start <= decision_t",
        "n",
        "blinks_clean",
        "yes",
    )
    add(
        "frac_window_in_current_step",
        "overlap([w_lo,w_hi], step) / window_len_s",
        "ratio",
        "derived",
        "yes",
    )

    df = pd.DataFrame(rows, columns=["name", "formula", "units", "source", "deploy_feasible", "notes"])

    lines = ["# Feature dictionary — `X_window.parquet`", "", f"Generated by `04_extract_features_window.py`. Window = {WINDOW_LEN_S}s, stride = {STRIDE_S}s.", ""]
    lines.append("| name | formula | units | source | deploy_feasible | notes |")
    lines.append("|---|---|---|---|---|---|")
    for _, r in df.iterrows():
        lines.append(
            f"| `{r['name']}` | {r['formula']} | {r['units']} | {r['source']} | {r['deploy_feasible']} | {r['notes']} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed_root", type=Path, default=PROCESSED_ROOT)
    ap.add_argument(
        "--labels_csv",
        type=Path,
        default=None,
        help="Optional CSV with columns (session_uid, step_number, workload_label).",
    )
    args = ap.parse_args(argv)

    sidx_path = args.processed_root / "session_index.csv"
    bl_path = args.processed_root / "baselines.csv"
    if not sidx_path.is_file() or not bl_path.is_file():
        print("ERROR: stages 01 and 02 must be completed first.")
        return 2
    sidx = pd.read_csv(sidx_path)
    baselines = pd.read_csv(bl_path).set_index("session_uid")

    labels = None
    if args.labels_csv and args.labels_csv.is_file():
        labels = pd.read_csv(args.labels_csv)
        need = {"session_uid", "step_number", "workload_label"}
        if not need.issubset(set(labels.columns)):
            print(f"ERROR: labels_csv must have columns {need}; got {list(labels.columns)}")
            return 2
        labels = labels.set_index(["session_uid", "step_number"])

    per_proc_rows: dict[str, list[pd.DataFrame]] = {slug: [] for slug in PROCEDURE_ID_TO_SLUG.values()}
    summary_rows: list[dict] = []

    for _, row in sidx.iterrows():
        session_uid = str(row["session_uid"])
        baselines_row = baselines.loc[session_uid] if session_uid in baselines.index else pd.Series(dtype=float)
        sd = _load_session(row, baselines_row, args.processed_root)
        if sd is None:
            continue
        df_feat = _featurize_session(sd)
        if df_feat.empty:
            print(f"  ! {session_uid}: no windows generated")
            continue

        if labels is not None:
            keys = list(zip(df_feat["session_uid"], df_feat["step_number"].astype("Int64")))
            df_feat["workload_label"] = [
                labels["workload_label"].get(k, pd.NA) for k in keys
            ]

        per_proc_rows.setdefault(sd.procedure_slug, []).append(df_feat)

        valid = df_feat["valid"].astype(bool).sum()
        with_label = (
            int(df_feat["workload_label"].notna().sum()) if labels is not None else 0
        )
        print(
            f"  {session_uid}: {len(df_feat)} windows  "
            f"(valid={valid}, w/ label={with_label})"
        )
        summary_rows.append(
            {
                "session_uid": session_uid,
                "procedure_slug": sd.procedure_slug,
                "n_windows": len(df_feat),
                "n_valid": int(valid),
                "n_with_label": with_label,
            }
        )

    n_total = 0
    for slug, frames in per_proc_rows.items():
        if not frames:
            continue
        out_dir = args.processed_root / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        full = pd.concat(frames, ignore_index=True)
        # Reorder columns: keys first, then features, then label
        feat_cols = [c for c in full.columns if c not in PRIMARY_KEY_COLS + QC_COLS + ["workload_label"]]
        ordered = PRIMARY_KEY_COLS + feat_cols + QC_COLS + ["workload_label"]
        full = full[[c for c in ordered if c in full.columns]]
        out_path = out_dir / "X_window.parquet"
        full.to_parquet(out_path, index=False)
        n_total += len(full)
        sample = full.sample(n=min(len(full), max(50, len(full) // 20)), random_state=0)
        sample.to_csv(out_dir / "X_window_sample.csv", index=False)
        print(f"  wrote {out_path}  ({len(full)} rows)")

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(args.processed_root / "X_window_summary.csv", index=False)
    print(f"\nTotal windows across all procedures: {n_total}")

    fd_path = args.processed_root / "feature_dictionary.md"
    _write_feature_dictionary(fd_path)
    print(f"Wrote {fd_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
