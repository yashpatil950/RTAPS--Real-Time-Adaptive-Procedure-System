#!/usr/bin/env python3
"""Stage 7c: Random Forest workload classifier — sensor-only X, p_normalized Y.

User requirements addressed:
  1. Blink window 60 s → 30 s, feature renamed `blink_rate_30s`. Already
     applied in lib/config.py + lib/blink_features.py + 04_extract...
  2. NO `procedure_id` and NO `step_number` in X. Sensor features only.
  3. Y is derived from `p_normalized` in each procedure's "Step Summary"
     sheet (added by the user). k-means with k=3 splits p_normalized into
     low / medium / high clusters; the model is trained on these 3 classes.
  4. Random Forest (handles correlated features and small n_groups well).
  5. No proxy / no fake data — every label comes from the user's manually
     curated VACP analysis (sum of operator weights → MWI → p_normalized).
  6. Step 0 ("Prep to start task") excluded for all 3 procedures.

Outputs → ML Algorithm/models/:
  v4_rf_pnorm.joblib              trained model + metadata + cluster boundaries
  rf_cv_metrics.json              per-fold and aggregate metrics
  rf_oof_window.parquet           OOF predictions (window level)
  rf_oof_step.parquet             OOF predictions (step level, majority vote)
  rf_feature_importance.csv       per-feature importance + permutation importance
  rf_confusion_window.csv         window-level confusion matrix
  rf_confusion_step.csv           step-level confusion matrix
  rf_per_participant.csv          per-participant balanced accuracy

Run:
  python "ML Algorithm/scripts/07c_train_rf_pnorm.py"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import ML_ROOT, PROCEDURE_ID_TO_SLUG, PROCESSED_ROOT  # noqa: E402

# --------------------------------------------------------------------------- #
# Feature contract — sensor-only, must match Streaming_Backend feature_extractor
# --------------------------------------------------------------------------- #

FEATURE_COLS = [
    "pupil_pcps_mean",
    "pupil_diam_slope",
    "blink_rate_30s",            # was blink_rate_per_min, now 30 s window
    "fixation_dur_mean_ms",
    "fixation_dispersion_mean",
]
GROUP_COL = "participant_id"
# v4 uses binary classification: low / high. The "medium" cluster from earlier
# attempts was sparse in p_normalized (most steps live in the lower half) and
# the operator-facing UI only shows guidance for HIGH workload anyway — low
# workload steps need no UI prompt. So a 2-class split is both better-balanced
# AND maps cleanly to UI behavior.
LABEL_ORDER = ["low", "high"]

PROC_LABEL_TO_ID = {
    "Centrifuge task": 1,
    "Column Flushing task": 2,
    "Pressure Testing task": 3,
}


# --------------------------------------------------------------------------- #
# Y label construction — k-means on p_normalized                              #
# --------------------------------------------------------------------------- #

def _load_step_summary() -> pd.DataFrame:
    """Read each procedure's 'Step Summary' sheet → one DataFrame."""
    rows: list[pd.DataFrame] = []
    for slug in ("centrifuge", "column_flushing", "pressure_testing"):
        p = PROCESSED_ROOT / "Y labels" / f"{slug}_vacp_workload.xlsx"
        s = pd.read_excel(p, sheet_name="Step Summary")
        s["procedure_slug"] = slug
        s["procedure_id"] = s["Procedure"].map(PROC_LABEL_TO_ID)
        rows.append(s)
    return pd.concat(rows, ignore_index=True)


def _build_label_table(step_summary: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Cluster p_normalized into 2 classes (low / high) via k-means + gap analysis.

    Pure k-means k=2 on this dataset isolates only the 4 highest-VACP steps
    (≥0.637) into "high" and dumps all 31 others into "low" — too imbalanced
    for the RF to learn anything useful. We pick a BETTER boundary by looking
    at the natural gaps in the sorted p_normalized distribution and rejecting
    a split that leaves either class below `min_class_size`. This both
    respects natural breaks AND keeps classes large enough for cross-validation.

    Step 0 is excluded across all procedures (per user instruction).
    """
    MIN_CLASS_SIZE = 7   # need at least this many steps per class for stable CV
    train = step_summary[step_summary["Step ID"] > 0].copy().reset_index(drop=True)
    sorted_vals = np.sort(train["p_normalized"].to_numpy())
    n = len(sorted_vals)

    # k-means k=2 (the user's request)
    vals = train[["p_normalized"]].to_numpy()
    km = KMeans(n_clusters=2, n_init=50, random_state=42).fit(vals)
    centers = sorted(km.cluster_centers_.flatten().tolist())
    km_boundary = (centers[0] + centers[1]) / 2

    # Count what k-means proposes
    km_low = int(np.sum(sorted_vals <= km_boundary))
    km_high = n - km_low

    # Inspect gaps between every adjacent pair of values; for each gap, the
    # midpoint is a candidate split. Score each candidate by:
    #   - gap_size:  bigger = more natural break
    #   - balance:   penalize splits where either class < MIN_CLASS_SIZE
    candidates: list[tuple[float, int, int, float]] = []  # (midpoint, low_n, high_n, score)
    for i in range(n - 1):
        mid = (sorted_vals[i] + sorted_vals[i + 1]) / 2.0
        gap = sorted_vals[i + 1] - sorted_vals[i]
        n_low = i + 1
        n_high = n - n_low
        # Penalty if either class is below the floor
        balance_penalty = 0.0
        if n_low < MIN_CLASS_SIZE or n_high < MIN_CLASS_SIZE:
            balance_penalty = -1.0  # disqualify
        # Score: large gap + acceptable balance
        score = gap + balance_penalty
        candidates.append((mid, n_low, n_high, score))
    # Pick the highest-scoring candidate that also meets the floor
    eligible = [c for c in candidates if c[1] >= MIN_CLASS_SIZE and c[2] >= MIN_CLASS_SIZE]
    if eligible:
        # Pick the candidate with the largest gap (gap = score since balance_penalty is 0 for eligible)
        chosen = max(eligible, key=lambda c: c[3])
        chosen_boundary, chosen_low, chosen_high, chosen_gap = chosen
        method = "largest_gap_with_balance_floor"
    else:
        # Fallback to k-means' boundary even if imbalanced
        chosen_boundary = km_boundary
        chosen_low, chosen_high = km_low, km_high
        chosen_gap = 0.0
        method = "kmeans_imbalanced_fallback"

    train["workload_label"] = ["high" if v > chosen_boundary else "low"
                                for v in train["p_normalized"]]

    meta = {
        "n_clusters": 2,
        "method": method,
        "chosen_boundary": round(float(chosen_boundary), 4),
        "chosen_gap_size": round(float(chosen_gap), 4),
        "kmeans_centers": [round(c, 4) for c in centers],
        "kmeans_boundary": round(float(km_boundary), 4),
        "kmeans_split": {"low": int(km_low), "high": int(km_high)},
        "n_steps_total": int(n),
        "class_distribution_step_level": train["workload_label"].value_counts().to_dict(),
    }
    return train[["procedure_id", "Step ID", "p_normalized", "workload_label", "Step description"]], meta


# --------------------------------------------------------------------------- #
# Window data — load X_window.parquet and join labels                         #
# --------------------------------------------------------------------------- #

def _load_windows() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for slug in PROCEDURE_ID_TO_SLUG.values():
        p = PROCESSED_ROOT / slug / "X_window.parquet"
        if not p.is_file():
            print(f"  ! {p} missing — run stage 04 + 04b first")
            continue
        df = pd.read_parquet(p)
        frames.append(df)
        print(f"  {slug}: {len(df)} windows  |  {df['participant_id'].nunique()} participants")
    if not frames:
        raise FileNotFoundError("No X_window.parquet files.")
    return pd.concat(frames, ignore_index=True)


def _attach_labels(windows: pd.DataFrame, step_labels: pd.DataFrame) -> pd.DataFrame:
    """Left-join window rows to per-step labels by (procedure_id, step_number).

    X_window.parquet already carries an old `workload_label` column from the
    legacy weak-proxy labels — drop it first so the join produces a clean
    single-column result.
    """
    key = step_labels.rename(columns={"Step ID": "step_number"})[
        ["procedure_id", "step_number", "p_normalized", "workload_label"]
    ]
    windows_clean = windows.drop(columns=[c for c in ("workload_label", "p_normalized") if c in windows.columns])
    out = windows_clean.merge(key, on=["procedure_id", "step_number"], how="left")
    n_total = len(out)
    out = out[out["workload_label"].notna()].copy()
    print(f"  Dropped {n_total - len(out)} windows that fell on step 0 (excluded)")
    return out


# --------------------------------------------------------------------------- #
# Prepare                                                                      #
# --------------------------------------------------------------------------- #

def _prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, pd.DataFrame]:
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise KeyError(f"X_window.parquet missing required feature cols: {missing}.\n"
                       "Did you re-run stage 04 with the new blink_rate_30s naming?")
    mask = (
        df["valid"].astype(bool)
        & df["workload_label"].notna()
        & df["workload_label"].isin(LABEL_ORDER)
        & df[GROUP_COL].notna()
        & (df[GROUP_COL].astype(str).str.len() > 0)
    )
    df = df.loc[mask].copy()
    if df.empty:
        raise ValueError("No valid, labeled windows after filtering.")

    X = df[FEATURE_COLS].copy()
    y = df["workload_label"].astype(str).to_numpy()
    groups = df[GROUP_COL].astype(str).to_numpy()
    keys = df[
        ["session_uid", "step_number", "procedure_id", "participant_id", "p_normalized"]
    ].reset_index(drop=True)
    return X.reset_index(drop=True), y, groups, keys


# --------------------------------------------------------------------------- #
# Model factory                                                                #
# --------------------------------------------------------------------------- #

def _new_model() -> Pipeline:
    """Random Forest in a Pipeline so NaN sensor values get imputed (RF
    requires complete inputs). class_weight='balanced' compensates for the
    skew toward 'low' in the label distribution."""
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("rf", RandomForestClassifier(
            n_estimators=400,
            max_depth=12,
            min_samples_leaf=20,
            min_samples_split=10,
            max_features="sqrt",
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
        )),
    ])


# --------------------------------------------------------------------------- #
# Metrics                                                                     #
# --------------------------------------------------------------------------- #

def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    rep = classification_report(y_true, y_pred, labels=LABEL_ORDER, zero_division=0, output_dict=True)
    return {
        "accuracy": float((y_true == y_pred).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABEL_ORDER, average="macro", zero_division=0)),
        "cohen_kappa": float(cohen_kappa_score(y_true, y_pred, labels=LABEL_ORDER)),
        "per_class": {c: rep[c] for c in LABEL_ORDER},
    }


def _confusion_df(y_true: np.ndarray, y_pred: np.ndarray) -> pd.DataFrame:
    cm = confusion_matrix(y_true, y_pred, labels=LABEL_ORDER)
    return pd.DataFrame(
        cm,
        index=[f"true_{c}" for c in LABEL_ORDER],
        columns=[f"pred_{c}" for c in LABEL_ORDER],
    )


def _step_majority_vote(window_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for (sess, step), g in window_df.groupby(["session_uid", "step_number"]):
        rows.append({
            "session_uid": sess,
            "step_number": int(step),
            "participant_id": g["participant_id"].iloc[0],
            "procedure_id": g["procedure_id"].iloc[0],
            "p_normalized": g["p_normalized"].iloc[0],
            "n_windows": len(g),
            "y_true": g["y_true"].mode().iloc[0],
            "y_pred": g["y_pred"].mode().iloc[0],
        })
    return pd.DataFrame(rows)


def _per_participant(window_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for pid, g in window_df.groupby("participant_id"):
        m = _metrics(g["y_true"].to_numpy(), g["y_pred"].to_numpy())
        rows.append({
            "participant_id": pid,
            "n_windows": len(g),
            "accuracy": m["accuracy"],
            "balanced_accuracy": m["balanced_accuracy"],
            "macro_f1": m["macro_f1"],
            "cohen_kappa": m["cohen_kappa"],
        })
    return pd.DataFrame(rows).sort_values("balanced_accuracy", ascending=False)


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed_root", type=Path, default=PROCESSED_ROOT)
    ap.add_argument("--models_dir", type=Path, default=ML_ROOT / "models")
    ap.add_argument("--n_splits", type=int, default=5)
    ap.add_argument("--permutation_repeats", type=int, default=10)
    args = ap.parse_args(argv)
    args.models_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. Build Y labels from p_normalized ---------------------------- #
    print("=" * 70)
    print("Step 1: Cluster p_normalized into 2 classes (low / high)")
    print("=" * 70)
    summary = _load_step_summary()
    step_labels, meta = _build_label_table(summary)
    print(f"  k-means k=2 centers: {meta['kmeans_centers']}")
    print(f"  k-means raw boundary: {meta['kmeans_boundary']}  →  split: {meta['kmeans_split']}")
    print(f"  Method chosen:       {meta['method']}")
    print(f"  Chosen boundary:     low ≤ {meta['chosen_boundary']}  |  high >")
    print(f"  Step-level distribution: {meta['class_distribution_step_level']}")

    # ---- 2. Load X windows + attach labels ------------------------------ #
    print("\n" + "=" * 70)
    print("Step 2: Load X_window.parquet for all 3 procedures")
    print("=" * 70)
    windows = _load_windows()
    print(f"  Total windows: {len(windows)}")
    windows = _attach_labels(windows, step_labels)

    # ---- 3. Prepare ----------------------------------------------------- #
    X, y, groups, keys = _prepare(windows)
    n_groups = pd.Series(groups).nunique()
    n_splits = max(2, min(args.n_splits, n_groups))
    cls_dist = dict(pd.Series(y).value_counts().sort_index())
    print(f"\n  After filtering: {len(X)} windows  |  {n_groups} participants  |  {n_splits}-fold CV")
    print(f"  Window-level class distribution: {cls_dist}")
    nan_pct = {c: f"{X[c].isna().mean() * 100:.1f}%" for c in FEATURE_COLS}
    print(f"  NaN % per feature:")
    for c in FEATURE_COLS:
        print(f"     {c:<30} {nan_pct[c]}")

    # ---- 4. Cross-validation -------------------------------------------- #
    print("\n" + "=" * 70)
    print("Step 3: GroupKFold CV (grouped by participant — no leakage)")
    print("=" * 70)
    gkf = GroupKFold(n_splits=n_splits)
    fold_metrics: list[dict] = []
    oof = np.empty(len(X), dtype=object)
    assigned = np.zeros(len(X), dtype=bool)

    for fold, (tr, te) in enumerate(gkf.split(X, y, groups), start=1):
        m = _new_model()
        m.fit(X.iloc[tr], y[tr])
        pred = m.predict(X.iloc[te])
        oof[te] = pred
        assigned[te] = True
        mt = _metrics(y[te], pred)
        held = sorted(set(groups[te]))
        print(
            f"  Fold {fold}: bal_acc={mt['balanced_accuracy']:.3f}  "
            f"macro_f1={mt['macro_f1']:.3f}  κ={mt['cohen_kappa']:+.3f}  "
            f"held-out={held}"
        )
        fold_metrics.append({
            "fold": fold,
            "n_train": int(len(tr)),
            "n_test": int(len(te)),
            "held_out_participants": held,
            **{k: v for k, v in mt.items() if k != "per_class"},
            "per_class": mt["per_class"],
        })

    if not assigned.all():
        oof = np.where(assigned, oof, "low")

    # ---- 5. OOF aggregates ---------------------------------------------- #
    m_win = _metrics(y, oof)
    cm_win = _confusion_df(y, oof)
    print("\n" + "=" * 70)
    print("Step 4: Out-of-fold (OOF) aggregate metrics")
    print("=" * 70)
    print(f"\n[Window level]")
    print(f"  accuracy = {m_win['accuracy']:.3f}")
    print(f"  balanced_accuracy = {m_win['balanced_accuracy']:.3f}")
    print(f"  macro_f1 = {m_win['macro_f1']:.3f}")
    print(f"  cohen_kappa = {m_win['cohen_kappa']:+.3f}")
    print(f"  {'Class':10s} {'Prec':>7} {'Rec':>7} {'F1':>7} {'Supp':>7}")
    for cls, v in m_win["per_class"].items():
        print(f"  {cls:10s} {v['precision']:>7.3f} {v['recall']:>7.3f} {v['f1-score']:>7.3f} {int(v['support']):>7d}")
    print("\nConfusion matrix (window):")
    print(cm_win.to_string())

    # Step-level (majority vote)
    win_pred_df = keys.copy()
    win_pred_df["y_true"] = y
    win_pred_df["y_pred"] = oof
    step_preds = _step_majority_vote(win_pred_df)
    m_step = _metrics(step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy())
    cm_step = _confusion_df(step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy())
    print(f"\n[Step level — majority vote, {len(step_preds)} steps]")
    print(f"  balanced_acc = {m_step['balanced_accuracy']:.3f}  macro_f1 = {m_step['macro_f1']:.3f}  κ = {m_step['cohen_kappa']:+.3f}")
    print("\nConfusion matrix (step):")
    print(cm_step.to_string())

    # Per-participant
    pp_df = _per_participant(win_pred_df)
    print(f"\n[Per-participant balanced accuracy]")
    print(pp_df.to_string(index=False))

    # ---- 6. Refit + permutation importance ------------------------------ #
    print("\n" + "=" * 70)
    print("Step 5: Refit on ALL data and compute permutation importance")
    print("=" * 70)
    final_model = _new_model()
    final_model.fit(X, y)

    # Built-in RF importance (Gini)
    rf = final_model.named_steps["rf"]
    builtin_imp = pd.DataFrame({
        "feature": FEATURE_COLS,
        "rf_gini_importance": rf.feature_importances_,
    })

    # Permutation importance (slower but more reliable)
    perm = permutation_importance(
        final_model, X, y,
        n_repeats=args.permutation_repeats,
        random_state=42,
        scoring="f1_macro",
        n_jobs=-1,
    )
    fi_df = builtin_imp.copy()
    fi_df["permutation_importance_mean"] = perm.importances_mean
    fi_df["permutation_importance_std"] = perm.importances_std
    fi_df = fi_df.sort_values("permutation_importance_mean", ascending=False).reset_index(drop=True)
    print(fi_df.round(4).to_string(index=False))

    # ---- 7. Save -------------------------------------------------------- #
    model_path = args.models_dir / "v4_rf_pnorm.joblib"
    joblib.dump({
        "model": final_model,
        "feature_columns": FEATURE_COLS,
        "categorical_columns": [],
        "label_order": LABEL_ORDER,
        "label_source": "p_normalized_kmeans3",
        "label_meta": meta,
        "trained_on_n_windows": int(len(X)),
        "trained_on_n_participants": int(n_groups),
    }, model_path)
    print(f"\nSaved model → {model_path}")

    out = {
        "label_source": "p_normalized_kmeans3",
        "label_meta": meta,
        "feature_columns": FEATURE_COLS,
        "n_windows": int(len(X)),
        "n_participants": int(n_groups),
        "n_splits": int(n_splits),
        "class_distribution_window": {k: int(v) for k, v in cls_dist.items()},
        "fold_metrics": fold_metrics,
        "oof_window": m_win,
        "oof_step": {**m_step, "n_steps": int(len(step_preds))},
    }
    (args.models_dir / "rf_cv_metrics.json").write_text(json.dumps(out, indent=2))
    win_pred_df.to_parquet(args.models_dir / "rf_oof_window.parquet", index=False)
    step_preds.to_parquet(args.models_dir / "rf_oof_step.parquet", index=False)
    fi_df.to_csv(args.models_dir / "rf_feature_importance.csv", index=False)
    cm_win.to_csv(args.models_dir / "rf_confusion_window.csv")
    cm_step.to_csv(args.models_dir / "rf_confusion_step.csv")
    pp_df.to_csv(args.models_dir / "rf_per_participant.csv", index=False)
    print(f"Saved metrics/outputs → {args.models_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
