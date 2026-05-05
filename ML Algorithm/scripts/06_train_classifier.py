#!/usr/bin/env python3
"""Stage 6: train the workload classifier on the 8 features defined in
`X_FEATURES.md`.

Single source of truth for features at training time:

    pupil_pcps_mean
    pupil_diam_slope
    blink_rate_per_min
    fixation_dur_mean_ms
    fixation_dispersion_mean
    procedure_id              (categorical)
    step_number
    cumulative_session_time_s

The same 8 columns must be produced live by the streaming backend at serving
time (see `streaming_backend/`). Anything else is intentionally excluded — see
`X_FEATURES.md` §4 for the rationale.

Pipeline:

    1. Load `X_window.parquet` from every procedure under `_processed/`.
    2. Concatenate; keep only rows with `valid == True` and a non-null
       `workload_label`.
    3. Select FEATURE_COLS + (participant_id as group key, workload_label as
       target).
    4. GroupKFold over participant_id so participants never leak across folds.
    5. Per fold: fit HistGradientBoostingClassifier (handles NaNs natively;
       `procedure_id` declared categorical), score on held-out fold.
    6. Aggregate window-level OOF predictions to step-level via majority vote.
    7. Refit on ALL data → save final model + permutation feature importance.

Outputs (all under `models/`):
    v1_hgb_weak.joblib              fitted final model + label order + features
    cv_metrics.json                 per-fold and aggregate scores
    oof_predictions_window.parquet  OOF preds with true labels (window level)
    oof_predictions_step.parquet    OOF preds aggregated to step level
    feature_importance.csv          permutation importance on the refit model
    confusion_matrix_window.csv     window-level OOF confusion matrix
    confusion_matrix_step.csv       step-level OOF confusion matrix

Run:
    python "ML Algorithm/scripts/06_train_classifier.py"
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
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import GroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import ML_ROOT, PROCEDURE_ID_TO_SLUG, PROCESSED_ROOT  # noqa: E402

# ---- The contract with X_FEATURES.md ------------------------------------- #

FEATURE_COLS = [
    "pupil_pcps_mean",
    "pupil_diam_slope",
    "blink_rate_per_min",
    "fixation_dur_mean_ms",
    "fixation_dispersion_mean",
    "procedure_id",
    "step_number",
    "cumulative_session_time_s",
]
CATEGORICAL_COLS = ["procedure_id"]  # subset of FEATURE_COLS
GROUP_COL = "participant_id"
LABEL_COL = "workload_label"
LABEL_ORDER = ["low", "medium", "high"]

# -------------------------------------------------------------------------- #


def _load_all_windows(processed_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for slug in PROCEDURE_ID_TO_SLUG.values():
        p = processed_root / slug / "X_window.parquet"
        if not p.is_file():
            print(f"  ! {p} missing; skipping {slug}")
            continue
        df = pd.read_parquet(p)
        frames.append(df)
        print(f"  loaded {slug}: {len(df)} rows")
    if not frames:
        raise FileNotFoundError("No X_window.parquet found under processed_root.")
    return pd.concat(frames, ignore_index=True)


def _prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, pd.DataFrame]:
    """Filter to valid + labeled, return (X_df, y, groups, key_df)."""
    needed = set(FEATURE_COLS + [GROUP_COL, LABEL_COL, "valid", "session_uid", "step_number"])
    missing = needed - set(df.columns)
    if missing:
        raise KeyError(f"X_window.parquet missing columns: {sorted(missing)}")

    mask = (
        df["valid"].astype(bool)
        & df[LABEL_COL].notna()
        & df[LABEL_COL].isin(LABEL_ORDER)
        & df[GROUP_COL].notna()
        & (df[GROUP_COL].astype(str).str.len() > 0)
    )
    df = df.loc[mask].copy()
    if df.empty:
        raise ValueError("No labeled, valid windows after filtering.")

    X = df[FEATURE_COLS].copy()
    # Cast categorical -> pandas category so HGB sees it as categorical
    X["procedure_id"] = X["procedure_id"].astype("Int64").astype("category")
    y = df[LABEL_COL].astype(str).to_numpy()
    groups = df[GROUP_COL].astype(str).to_numpy()
    keys = df[["session_uid", "step_number", "procedure_id", "participant_id"]].reset_index(drop=True)
    return X.reset_index(drop=True), y, groups, keys


def _new_model() -> HistGradientBoostingClassifier:
    cat_idx = [FEATURE_COLS.index(c) for c in CATEGORICAL_COLS]
    return HistGradientBoostingClassifier(
        max_depth=6,
        learning_rate=0.05,
        max_iter=400,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=25,
        random_state=42,
        categorical_features=cat_idx,
    )


def _per_class_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    rep = classification_report(
        y_true, y_pred, labels=LABEL_ORDER, zero_division=0, output_dict=True
    )
    return {c: rep[c] for c in LABEL_ORDER}


def _confusion(y_true: np.ndarray, y_pred: np.ndarray) -> pd.DataFrame:
    cm = confusion_matrix(y_true, y_pred, labels=LABEL_ORDER)
    return pd.DataFrame(
        cm,
        index=[f"true_{c}" for c in LABEL_ORDER],
        columns=[f"pred_{c}" for c in LABEL_ORDER],
    )


def _step_majority_vote(window_preds: pd.DataFrame) -> pd.DataFrame:
    """One predicted label per (session_uid, step_number): plurality of windows."""
    rows: list[dict] = []
    for (sess, step), g in window_preds.groupby(["session_uid", "step_number"]):
        truth = g["y_true"].mode().iloc[0]
        pred = g["y_pred"].mode().iloc[0]
        rows.append(
            {
                "session_uid": sess,
                "step_number": int(step),
                "participant_id": g["participant_id"].iloc[0],
                "procedure_id": g["procedure_id"].iloc[0],
                "n_windows": len(g),
                "y_true": truth,
                "y_pred": pred,
            }
        )
    return pd.DataFrame(rows)


# -------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed_root", type=Path, default=PROCESSED_ROOT)
    ap.add_argument("--models_dir", type=Path, default=ML_ROOT / "models")
    ap.add_argument("--n_splits", type=int, default=5)
    ap.add_argument("--permutation_repeats", type=int, default=10)
    args = ap.parse_args(argv)

    args.models_dir.mkdir(parents=True, exist_ok=True)

    print("Loading windowed features...")
    df_all = _load_all_windows(args.processed_root)
    print(f"  total: {len(df_all)} rows  ({df_all['session_uid'].nunique()} sessions)")

    print("\nFiltering and selecting the 8 features from X_FEATURES.md...")
    X, y, groups, keys = _prepare(df_all)
    n_groups = pd.Series(groups).nunique()
    n_splits = max(2, min(args.n_splits, n_groups))
    print(f"  rows: {len(X)}   participants: {n_groups}   folds: {n_splits}")
    print(f"  feature columns ({len(FEATURE_COLS)}): {FEATURE_COLS}")
    cls_dist = pd.Series(y).value_counts().to_dict()
    print(f"  class distribution: {cls_dist}")

    # ---- Cross-validation ------------------------------------------------ #
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

        macro_f1 = f1_score(y[te], pred, labels=LABEL_ORDER, average="macro", zero_division=0)
        bal_acc = balanced_accuracy_score(y[te], pred)
        acc = (pred == y[te]).mean()
        per_class = _per_class_metrics(y[te], pred)
        held_out = sorted(set(groups[te]))
        print(
            f"  fold {fold}: macro_f1={macro_f1:.3f}  balanced_acc={bal_acc:.3f}  "
            f"acc={acc:.3f}   held-out participants: {held_out}"
        )
        fold_metrics.append(
            {
                "fold": fold,
                "n_train": int(len(tr)),
                "n_test": int(len(te)),
                "held_out_participants": held_out,
                "macro_f1": float(macro_f1),
                "balanced_acc": float(bal_acc),
                "accuracy": float(acc),
                "per_class": per_class,
            }
        )

    if not oof_assigned.all():
        # GroupKFold should cover every row exactly once, but guard anyway.
        miss = (~oof_assigned).sum()
        print(f"  ! {miss} rows had no OOF prediction (group not in any test fold).")
        oof_pred = np.where(oof_assigned, oof_pred, "low")  # safe default for downstream

    # Aggregate OOF metrics ----------------------------------------------- #
    macro_f1 = f1_score(y, oof_pred, labels=LABEL_ORDER, average="macro", zero_division=0)
    bal_acc = balanced_accuracy_score(y, oof_pred)
    acc = (oof_pred == y).mean()
    cm_window = _confusion(y, oof_pred)
    per_class_overall = _per_class_metrics(y, oof_pred)

    print("\nAggregate OOF (window level):")
    print(f"  macro_f1={macro_f1:.3f}  balanced_acc={bal_acc:.3f}  accuracy={acc:.3f}")
    print(cm_window.to_string())

    # Step-level aggregation ---------------------------------------------- #
    window_pred_df = keys.copy()
    window_pred_df["y_true"] = y
    window_pred_df["y_pred"] = oof_pred
    step_preds = _step_majority_vote(window_pred_df)
    macro_f1_step = f1_score(
        step_preds["y_true"], step_preds["y_pred"],
        labels=LABEL_ORDER, average="macro", zero_division=0,
    )
    bal_acc_step = balanced_accuracy_score(step_preds["y_true"], step_preds["y_pred"])
    acc_step = (step_preds["y_true"] == step_preds["y_pred"]).mean()
    cm_step = _confusion(step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy())
    per_class_step = _per_class_metrics(
        step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy()
    )

    print("\nAggregate OOF (step level, majority-vote of windows):")
    print(f"  macro_f1={macro_f1_step:.3f}  balanced_acc={bal_acc_step:.3f}  accuracy={acc_step:.3f}")
    print(cm_step.to_string())

    # Refit on ALL data + feature importance ------------------------------ #
    print("\nRefitting on all data for the final model...")
    final_model = _new_model()
    final_model.fit(X, y)

    print("Computing permutation feature importance (this is the slow step)...")
    perm = permutation_importance(
        final_model, X, y,
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

    # ---- Persist outputs ------------------------------------------------- #
    model_path = args.models_dir / "v1_hgb_weak.joblib"
    joblib.dump(
        {
            "model": final_model,
            "feature_columns": FEATURE_COLS,
            "categorical_columns": CATEGORICAL_COLS,
            "label_order": LABEL_ORDER,
            "label_source": "weak_rule_v1 (proxy from exceededThreshold + subStepsShown)",
            "trained_on_n_windows": int(len(X)),
            "trained_on_n_participants": int(n_groups),
        },
        model_path,
    )
    print(f"\nSaved model -> {model_path}")

    metrics = {
        "n_windows_total": int(len(X)),
        "n_participants": int(n_groups),
        "n_splits": int(n_splits),
        "feature_count": len(FEATURE_COLS),
        "feature_columns": FEATURE_COLS,
        "categorical_features": CATEGORICAL_COLS,
        "label_order": LABEL_ORDER,
        "label_source": "weak_rule_v1",
        "class_distribution": {k: int(v) for k, v in cls_dist.items()},
        "fold_metrics": fold_metrics,
        "oof_window": {
            "macro_f1": float(macro_f1),
            "balanced_acc": float(bal_acc),
            "accuracy": float(acc),
            "per_class": per_class_overall,
        },
        "oof_step": {
            "macro_f1": float(macro_f1_step),
            "balanced_acc": float(bal_acc_step),
            "accuracy": float(acc_step),
            "per_class": per_class_step,
            "n_steps": int(len(step_preds)),
        },
    }
    (args.models_dir / "cv_metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"Saved metrics -> {args.models_dir / 'cv_metrics.json'}")

    window_pred_df.to_parquet(args.models_dir / "oof_predictions_window.parquet", index=False)
    step_preds.to_parquet(args.models_dir / "oof_predictions_step.parquet", index=False)
    fi_df.to_csv(args.models_dir / "feature_importance.csv", index=False)
    cm_window.to_csv(args.models_dir / "confusion_matrix_window.csv")
    cm_step.to_csv(args.models_dir / "confusion_matrix_step.csv")
    print(f"Saved OOF predictions, feature importance, and confusion matrices -> {args.models_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
