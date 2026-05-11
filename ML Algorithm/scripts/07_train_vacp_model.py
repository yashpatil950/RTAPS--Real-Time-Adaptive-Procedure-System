#!/usr/bin/env python3
"""
Stage 7: Train the VACP-labeled workload classifier.

Uses ground-truth VACP workload labels (Zhu et al., 2025 methodology)
instead of the proxy labels used in Stage 6.

Features (7, per X_FEATURES.md v2):
    pupil_pcps_mean, blink_rate_per_min,
    fixation_dur_mean_ms, fixation_dispersion_mean,
    procedure_id, step_number, cumulative_session_time_s

Labels: low / medium / high  (global tertile split across all 35 labeled steps)
Groups: participant_id (GroupKFold — no participant leaks across folds)

Step 0 excluded for all 3 procedures (pre-task prep, not a rated step).

Outputs → ML Algorithm/models/:
    v2_hgb_vacp.joblib           trained model + metadata
    vacp_cv_metrics.json         per-fold + aggregate scores
    vacp_oof_window.parquet      OOF predictions (window level)
    vacp_oof_step.parquet        OOF predictions (step level, majority vote)
    vacp_feature_importance.csv  permutation importance
    vacp_confusion_window.csv    confusion matrix (window level)
    vacp_confusion_step.csv      confusion matrix (step level)

Run:
    python "ML Algorithm/scripts/07_train_vacp_model.py"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import ML_ROOT, PROCEDURE_ID_TO_SLUG, PROCESSED_ROOT  # noqa: E402

# --------------------------------------------------------------------------- #
# Feature contract (must match Streaming_Backend/app/feature_extractor.py)    #
# --------------------------------------------------------------------------- #

FEATURE_COLS = [
    "pupil_pcps_mean",
    "blink_rate_per_min",
    "fixation_dur_mean_ms",
    "fixation_dispersion_mean",
    "procedure_id",
    "step_number",
    "cumulative_session_time_s",
]
CATEGORICAL_COLS = ["procedure_id"]
GROUP_COL = "participant_id"
LABEL_COL = "workload_label"
LABEL_ORDER = ["low", "medium", "high"]

# --------------------------------------------------------------------------- #
# VACP ground-truth scores — (procedure_id, step_number) → VACP total         #
#                                                                              #
# Source: centrifuge_vacp_workload.xlsx, column_flushing_vacp_workload.xlsx,  #
#         pressure_testing_vacp_workload.xlsx  (Y labels folder)              #
# Method: sum of VACP weights per step (Zhu et al. 2025 reference table)      #
# Step 0 excluded for all procedures (pre-task prep).                         #
#                                                                              #
# Centrifuge (proc_id=1):  VACP step_ids 1-8  → step_number 1-8              #
# Col. flushing (proc_id=2): VACP step_ids 1-13 → step_number 1-13           #
# Pressure test (proc_id=3): VACP step_ids 1-14 → step_number 1-14           #
# --------------------------------------------------------------------------- #

VACP_SCORES: dict[tuple[int, int], float] = {
    # Centrifuge (procedure_id = 1)
    (1, 1):  81.0,   # Take sample from bulk oil treater
    (1, 2): 173.5,   # Fill centrifuge tubes to 100 ml mark
    (1, 3): 129.0,   # [Step 3 — added/updated in VACP file]
    (1, 4):  25.6,   # Place tubes on opposite sides for balance
    (1, 5):  34.3,   # Spin centrifuge 5 min @ 70% power
    (1, 6):  64.4,   # Obtain BS&W readings
    (1, 7):  25.6,   # Average results from two tubes
    (1, 8):  13.9,   # If questionable, take more samples
    # Column flushing (procedure_id = 2)
    (2, 1):  32.1,   # Have CRO put in manual control
    (2, 2):  52.8,   # Have CRO communicate when controller in manual
    (2, 3):  42.7,   # Close lower isolation valve
    (2, 4):  42.7,   # Close upper isolation valve
    (2, 5):  38.6,   # Remove plug
    (2, 6):   9.8,   # Open drain valve at bottom of cage
    (2, 7):   8.6,   # Drain fluids in bucket
    (2, 8):  47.0,   # Remove plug and open vent at top of cage float
    (2, 9): 108.4,   # Close vent valve and re-install plug
    (2, 10): 24.2,   # Close drain valve and re-install plug
    (2, 11): 15.7,   # Open manual valve - upper isolation
    (2, 12): 26.6,   # Open manual valve - lower isolation
    (2, 13): 55.4,   # Observe fluid rise and ILIC return to normal
    # Pressure testing (procedure_id = 3)
    (3, 1):  30.5,   # Notify Control Room
    (3, 2):  31.6,   # Have CRO place PST-113 in Override/Bypass
    (3, 3):  17.9,   # Close PST-113 isolation valves
    (3, 4):   8.6,   # Make sure test connection is depressured
    (3, 5):  23.2,   # Connect external pressure testing source
    (3, 6): 140.2,   # Increase test pressure until PSH is tripped
    (3, 7):   0.0,   # Reduce pressure until PSH is reset (system wait)
    (3, 8):  67.1,   # Reduce test pressure until PSL is tripped
    (3, 9):  14.4,   # Reduce test pressure completely
    (3, 10): 21.4,   # Disconnect test pressure source
    (3, 11): 50.3,   # Open PST-113 isolation valve
    (3, 12): 30.7,   # Verify pressure at safe operating limits
    (3, 13): 38.1,   # Remove Override/Bypass
    (3, 14): 32.5,   # Notify CRO ready to return to service
}


# --------------------------------------------------------------------------- #
# Label thresholds                                                             #
# --------------------------------------------------------------------------- #

def _compute_thresholds() -> tuple[float, float]:
    """Global tertile thresholds across all 35 labeled steps."""
    scores = np.array(list(VACP_SCORES.values()))
    return float(np.quantile(scores, 1 / 3)), float(np.quantile(scores, 2 / 3))


def vacp_to_label(score: float, t33: float, t66: float) -> str:
    if score <= t33:
        return "low"
    elif score <= t66:
        return "medium"
    else:
        return "high"


# --------------------------------------------------------------------------- #
# Data loading                                                                 #
# --------------------------------------------------------------------------- #

def _load_windows(processed_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for slug in PROCEDURE_ID_TO_SLUG.values():
        p = processed_root / slug / "X_window.parquet"
        if not p.is_file():
            print(f"  ! {p} missing — skipping {slug}")
            continue
        df = pd.read_parquet(p)
        frames.append(df)
        print(f"  {slug}: {len(df)} windows, {df['session_uid'].nunique()} sessions, "
              f"{df['participant_id'].nunique()} participants")
    if not frames:
        raise FileNotFoundError("No X_window.parquet files found under processed_root.")
    return pd.concat(frames, ignore_index=True)


def _attach_vacp_labels(df: pd.DataFrame, t33: float, t66: float) -> pd.DataFrame:
    """Replace proxy workload_label with VACP-derived label; drop unlabeled rows."""
    df = df.copy()
    keys = list(zip(df["procedure_id"].astype(int), df["step_number"].astype(int)))
    df["vacp_score"] = [VACP_SCORES.get(k) for k in keys]
    df["workload_label"] = df["vacp_score"].apply(
        lambda s: vacp_to_label(s, t33, t66) if s is not None else None
    )
    before = len(df)
    df = df[df["workload_label"].notna()].copy()
    dropped = before - len(df)
    if dropped:
        print(f"  Dropped {dropped} windows with no VACP label "
              f"(step not in mapping — typically col_flushing step 14)")
    return df


# --------------------------------------------------------------------------- #
# Prepare                                                                      #
# --------------------------------------------------------------------------- #

def _prepare(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, pd.DataFrame]:
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
    X["procedure_id"] = X["procedure_id"].astype("Int64").astype("category")
    y = df["workload_label"].astype(str).to_numpy()
    groups = df[GROUP_COL].astype(str).to_numpy()
    keys = df[
        ["session_uid", "step_number", "procedure_id", "participant_id", "vacp_score"]
    ].reset_index(drop=True)
    return X.reset_index(drop=True), y, groups, keys


# --------------------------------------------------------------------------- #
# Model factory                                                                #
# --------------------------------------------------------------------------- #

def _new_model() -> HistGradientBoostingClassifier:
    cat_idx = [FEATURE_COLS.index(c) for c in CATEGORICAL_COLS]
    return HistGradientBoostingClassifier(
        max_depth=4,
        learning_rate=0.05,
        max_iter=500,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=30,
        random_state=42,
        categorical_features=cat_idx,
    )


# --------------------------------------------------------------------------- #
# Metrics                                                                      #
# --------------------------------------------------------------------------- #

def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    rep = classification_report(
        y_true, y_pred, labels=LABEL_ORDER, zero_division=0, output_dict=True
    )
    return {
        "accuracy": float((y_true == y_pred).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(
            f1_score(y_true, y_pred, labels=LABEL_ORDER, average="macro", zero_division=0)
        ),
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
        rows.append(
            {
                "session_uid": sess,
                "step_number": int(step),
                "participant_id": g["participant_id"].iloc[0],
                "procedure_id": g["procedure_id"].iloc[0],
                "vacp_score": g["vacp_score"].iloc[0],
                "n_windows": len(g),
                "y_true": g["y_true"].mode().iloc[0],
                "y_pred": g["y_pred"].mode().iloc[0],
            }
        )
    return pd.DataFrame(rows)


def _print_metrics(label: str, m: dict, extra: str = "") -> None:
    print(
        f"  {label}: accuracy={m['accuracy']:.3f}  "
        f"balanced_acc={m['balanced_accuracy']:.3f}  "
        f"macro_f1={m['macro_f1']:.3f}  "
        f"kappa={m['cohen_kappa']:.3f}{extra}"
    )
    print(f"  {'Class':8s}  {'Precision':>10s}  {'Recall':>8s}  {'F1':>8s}  {'Support':>8s}")
    for cls, v in m["per_class"].items():
        print(
            f"  {cls:8s}  {v['precision']:>10.3f}  {v['recall']:>8.3f}"
            f"  {v['f1-score']:>8.3f}  {int(v['support']):>8d}"
        )


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed_root", type=Path, default=PROCESSED_ROOT)
    ap.add_argument("--models_dir", type=Path, default=ML_ROOT / "models")
    ap.add_argument("--n_splits", type=int, default=5)
    ap.add_argument("--permutation_repeats", type=int, default=15)
    args = ap.parse_args(argv)
    args.models_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. VACP thresholds ------------------------------------------------ #
    t33, t66 = _compute_thresholds()
    print("=" * 65)
    print("VACP label thresholds (global tertiles across 35 labeled steps)")
    print("=" * 65)
    print(f"  low    : VACP ≤ {t33:.2f}")
    print(f"  medium : {t33:.2f} < VACP ≤ {t66:.2f}")
    print(f"  high   : VACP > {t66:.2f}")
    print()
    print("Step-level labels:")
    for (pid, sn), score in sorted(VACP_SCORES.items()):
        lbl = vacp_to_label(score, t33, t66)
        slug = PROCEDURE_ID_TO_SLUG[pid]
        print(f"  {slug:20s} step {sn:2d}: VACP={score:6.1f}  →  {lbl}")

    # ---- 2. Load data ------------------------------------------------------- #
    print("\n" + "=" * 65)
    print("Loading windowed feature data")
    print("=" * 65)
    df_all = _load_windows(args.processed_root)
    print(f"  Total: {len(df_all)} windows  |  {df_all['session_uid'].nunique()} sessions")

    # ---- 3. Attach VACP labels --------------------------------------------- #
    print("\nAttaching VACP labels (step 0 excluded for all procedures)...")
    df_all = _attach_vacp_labels(df_all, t33, t66)

    # ---- 4. Prepare --------------------------------------------------------- #
    print("\nPreparing training set...")
    X, y, groups, keys = _prepare(df_all)
    n_groups = pd.Series(groups).nunique()
    n_splits = max(2, min(args.n_splits, n_groups))
    cls_dist = dict(pd.Series(y).value_counts().sort_index())

    print(f"  Windows after filtering : {len(X)}")
    print(f"  Participants (groups)   : {n_groups}  →  {n_splits}-fold CV")
    print(f"  Class distribution      : {cls_dist}")
    nan_pct = {c: f"{X[c].isna().mean() * 100:.1f}%" for c in FEATURE_COLS[:4]}
    print(f"  NaN % in sensor features: {nan_pct}")

    # ---- 5. GroupKFold cross-validation ------------------------------------- #
    print("\n" + "=" * 65)
    print("GroupKFold cross-validation  (grouped by participant_id)")
    print("=" * 65)
    gkf = GroupKFold(n_splits=n_splits)
    fold_metrics: list[dict] = []
    oof_pred = np.empty(len(X), dtype=object)
    oof_assigned = np.zeros(len(X), dtype=bool)

    for fold, (tr, te) in enumerate(gkf.split(X, y, groups), start=1):
        model = _new_model()
        model.fit(X.iloc[tr], y[tr])
        pred = model.predict(X.iloc[te])
        oof_pred[te] = pred
        oof_assigned[te] = True
        m = _metrics(y[te], pred)
        held = sorted(set(groups[te]))
        print(
            f"  Fold {fold}: balanced_acc={m['balanced_accuracy']:.3f}  "
            f"macro_f1={m['macro_f1']:.3f}  kappa={m['cohen_kappa']:.3f}  "
            f"held-out={held}"
        )
        fold_metrics.append(
            {
                "fold": fold,
                "n_train": int(len(tr)),
                "n_test": int(len(te)),
                "held_out_participants": held,
                "accuracy": m["accuracy"],
                "balanced_accuracy": m["balanced_accuracy"],
                "macro_f1": m["macro_f1"],
                "cohen_kappa": m["cohen_kappa"],
                "per_class": m["per_class"],
            }
        )

    if not oof_assigned.all():
        miss = int((~oof_assigned).sum())
        print(f"  ! {miss} windows had no OOF prediction — defaulting to 'low'")
        oof_pred = np.where(oof_assigned, oof_pred, "low")

    # ---- 6. OOF aggregate metrics ------------------------------------------ #
    print("\n" + "=" * 65)
    print("Out-of-fold (OOF) aggregate metrics")
    print("=" * 65)
    m_win = _metrics(y, oof_pred)
    cm_win = _confusion_df(y, oof_pred)
    print("\n[Window level]")
    _print_metrics("OOF", m_win)
    print("\nConfusion matrix (rows = true, cols = predicted):")
    print(cm_win.to_string())

    # ---- 7. Step-level aggregation ----------------------------------------- #
    win_pred_df = keys.copy()
    win_pred_df["y_true"] = y
    win_pred_df["y_pred"] = oof_pred
    step_preds = _step_majority_vote(win_pred_df)
    m_step = _metrics(
        step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy()
    )
    cm_step = _confusion_df(
        step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy()
    )
    print(f"\n[Step level — majority vote over windows]  ({len(step_preds)} steps)")
    _print_metrics("OOF", m_step)
    print("\nConfusion matrix (rows = true, cols = predicted):")
    print(cm_step.to_string())

    # ---- 8. Refit on all data ----------------------------------------------- #
    print("\n" + "=" * 65)
    print("Refitting on ALL data for the final deployed model")
    print("=" * 65)
    final_model = _new_model()
    final_model.fit(X, y)
    print(f"  Iterations used: {final_model.n_iter_}")

    print("\nComputing permutation feature importance (may take ~1 min)...")
    perm = permutation_importance(
        final_model,
        X,
        y,
        n_repeats=args.permutation_repeats,
        random_state=42,
        scoring="f1_macro",
        n_jobs=1,
    )
    fi_df = pd.DataFrame(
        {
            "feature": FEATURE_COLS,
            "importance_mean": perm.importances_mean,
            "importance_std": perm.importances_std,
        }
    ).sort_values("importance_mean", ascending=False).reset_index(drop=True)
    print(fi_df.to_string(index=False))

    # ---- 9. Persist --------------------------------------------------------- #
    model_path = args.models_dir / "v2_hgb_vacp.joblib"
    joblib.dump(
        {
            "model": final_model,
            "feature_columns": FEATURE_COLS,
            "categorical_columns": CATEGORICAL_COLS,
            "label_order": LABEL_ORDER,
            "label_source": "vacp_tertile_global",
            "vacp_thresholds": {"low_max": t33, "medium_max": t66},
            "vacp_scores": {f"{pid}_{sn}": s for (pid, sn), s in VACP_SCORES.items()},
            "trained_on_n_windows": int(len(X)),
            "trained_on_n_participants": int(n_groups),
        },
        model_path,
    )
    print(f"\nSaved model           → {model_path}")

    metrics_out = {
        "label_source": "vacp_tertile_global",
        "vacp_thresholds": {"t33": t33, "t66": t66},
        "n_windows": int(len(X)),
        "n_participants": int(n_groups),
        "n_splits": int(n_splits),
        "feature_columns": FEATURE_COLS,
        "class_distribution": {k: int(v) for k, v in cls_dist.items()},
        "fold_metrics": fold_metrics,
        "oof_window": m_win,
        "oof_step": {**m_step, "n_steps": int(len(step_preds))},
    }
    (args.models_dir / "vacp_cv_metrics.json").write_text(
        json.dumps(metrics_out, indent=2)
    )
    win_pred_df.to_parquet(args.models_dir / "vacp_oof_window.parquet", index=False)
    step_preds.to_parquet(args.models_dir / "vacp_oof_step.parquet", index=False)
    fi_df.to_csv(args.models_dir / "vacp_feature_importance.csv", index=False)
    cm_win.to_csv(args.models_dir / "vacp_confusion_window.csv")
    cm_step.to_csv(args.models_dir / "vacp_confusion_step.csv")
    print(f"Saved metrics/outputs → {args.models_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
