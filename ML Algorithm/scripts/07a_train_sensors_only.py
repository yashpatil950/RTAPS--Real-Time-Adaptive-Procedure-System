#!/usr/bin/env python3
"""Stage 7a: train a *sensors-only* workload classifier.

This is the model the user actually wants: predictions driven by eye-tracking
features (pupil, blink, fixation), NOT by step_number or procedure_id. The
"answer-key" features that let the previous model achieve 99.8% accuracy via
lookup are deliberately removed here.

Features (15, all sensor-derived):
    Raw (5):       pupil_pcps_mean, pupil_diam_slope, blink_rate_per_min,
                   fixation_dur_mean_ms, fixation_dispersion_mean
    Per-participant z (5): same names with `_zp` suffix
    Per-procedure z (5):   same names with `_zproc` suffix

Labels: VACP global tertiles  (low ≤ 25.6, 25.6 < medium ≤ 42.7, high > 42.7)
Groups: participant_id  (GroupKFold — no participant leaks across folds)

Outputs → ML Algorithm/models/:
    v3_hgb_sensors_only.joblib       trained model + metadata
    sensors_cv_metrics.json          per-fold + aggregate metrics
    sensors_oof_window.parquet       OOF predictions (window level)
    sensors_oof_step.parquet         OOF predictions (step level, majority)
    sensors_feature_importance.csv   permutation importance
    sensors_confusion_window.csv     confusion matrix (window)
    sensors_confusion_step.csv       confusion matrix (step)
    sensors_per_participant.csv      per-participant accuracy breakdown

Run:
    python "ML Algorithm/scripts/07a_train_sensors_only.py"
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
# Feature contract — sensor-derived only                                      #
# --------------------------------------------------------------------------- #

RAW_SENSORS = [
    "pupil_pcps_mean",
    "pupil_diam_slope",
    "blink_rate_per_min",
    "fixation_dur_mean_ms",
    "fixation_dispersion_mean",
]
ZP_SENSORS = [f"{c}_zp" for c in RAW_SENSORS]      # per-participant z-scored
ZPROC_SENSORS = [f"{c}_zproc" for c in RAW_SENSORS]  # per-procedure z-scored

FEATURE_COLS = RAW_SENSORS + ZP_SENSORS + ZPROC_SENSORS  # 15 features
GROUP_COL = "participant_id"
LABEL_ORDER = ["low", "medium", "high"]

# --------------------------------------------------------------------------- #
# VACP scores → labels                                                         #
# --------------------------------------------------------------------------- #

VACP_SCORES: dict[tuple[int, int], float] = {
    # Centrifuge
    (1, 1): 81.0, (1, 2): 173.5, (1, 3): 129.0, (1, 4): 25.6,
    (1, 5): 34.3, (1, 6): 64.4, (1, 7): 25.6, (1, 8): 13.9,
    # Column flushing
    (2, 1): 32.1, (2, 2): 52.8, (2, 3): 42.7, (2, 4): 42.7,
    (2, 5): 38.6, (2, 6): 9.8, (2, 7): 8.6, (2, 8): 47.0,
    (2, 9): 108.4, (2, 10): 24.2, (2, 11): 15.7, (2, 12): 26.6,
    (2, 13): 55.4,
    # Pressure testing
    (3, 1): 30.5, (3, 2): 31.6, (3, 3): 17.9, (3, 4): 8.6,
    (3, 5): 23.2, (3, 6): 140.2, (3, 7): 0.0, (3, 8): 67.1,
    (3, 9): 14.4, (3, 10): 21.4, (3, 11): 50.3, (3, 12): 30.7,
    (3, 13): 38.1, (3, 14): 32.5,
}


def _thresholds() -> tuple[float, float]:
    arr = np.array(list(VACP_SCORES.values()))
    return float(np.quantile(arr, 1 / 3)), float(np.quantile(arr, 2 / 3))


def _vacp_label(score: float, t33: float, t66: float) -> str:
    if score <= t33:
        return "low"
    if score <= t66:
        return "medium"
    return "high"


# --------------------------------------------------------------------------- #
# Data                                                                         #
# --------------------------------------------------------------------------- #

def _load_windows(processed_root: Path) -> pd.DataFrame:
    frames = []
    for slug in PROCEDURE_ID_TO_SLUG.values():
        p = processed_root / slug / "X_window.parquet"
        if not p.is_file():
            print(f"  ! {p} missing — skipping {slug}")
            continue
        df = pd.read_parquet(p)
        frames.append(df)
        print(f"  {slug}: {len(df)} windows  |  {df['participant_id'].nunique()} participants")
    if not frames:
        raise FileNotFoundError("No X_window.parquet found.")
    return pd.concat(frames, ignore_index=True)


def _attach_labels(df: pd.DataFrame, t33: float, t66: float) -> pd.DataFrame:
    df = df.copy()
    keys = list(zip(df["procedure_id"].astype(int), df["step_number"].astype(int)))
    df["vacp_score"] = [VACP_SCORES.get(k) for k in keys]
    df["workload_label"] = df["vacp_score"].apply(
        lambda s: _vacp_label(s, t33, t66) if pd.notna(s) else None
    )
    before = len(df)
    df = df[df["workload_label"].notna()]
    if before - len(df):
        print(f"  Dropped {before - len(df)} unlabeled windows (e.g. col_flushing step 14)")
    return df


def _prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, pd.DataFrame]:
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise KeyError(f"X_window.parquet missing required feature cols: {missing}.\n"
                       "Did you run 04b_add_normalized_features.py?")

    mask = (
        df["valid"].astype(bool)
        & df["workload_label"].notna()
        & df["workload_label"].isin(LABEL_ORDER)
        & df[GROUP_COL].notna()
        & (df[GROUP_COL].astype(str).str.len() > 0)
    )
    df = df.loc[mask].copy()
    if df.empty:
        raise ValueError("No valid, labeled windows.")

    X = df[FEATURE_COLS].copy()
    y = df["workload_label"].astype(str).to_numpy()
    groups = df[GROUP_COL].astype(str).to_numpy()
    keys = df[
        ["session_uid", "step_number", "procedure_id", "participant_id", "vacp_score"]
    ].reset_index(drop=True)
    return X.reset_index(drop=True), y, groups, keys


# --------------------------------------------------------------------------- #
# Model                                                                        #
# --------------------------------------------------------------------------- #

def _new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_depth=5,
        learning_rate=0.05,
        max_iter=500,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=30,
        random_state=42,
        # Re-weight classes inversely to frequency so the model doesn't just
        # learn "predict most common class always".
        class_weight="balanced",
    )


# --------------------------------------------------------------------------- #
# Metrics helpers                                                              #
# --------------------------------------------------------------------------- #

def _metrics(y_true, y_pred) -> dict:
    rep = classification_report(y_true, y_pred, labels=LABEL_ORDER, zero_division=0, output_dict=True)
    return {
        "accuracy": float((y_true == y_pred).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABEL_ORDER, average="macro", zero_division=0)),
        "cohen_kappa": float(cohen_kappa_score(y_true, y_pred, labels=LABEL_ORDER)),
        "per_class": {c: rep[c] for c in LABEL_ORDER},
    }


def _confusion_df(y_true, y_pred) -> pd.DataFrame:
    cm = confusion_matrix(y_true, y_pred, labels=LABEL_ORDER)
    return pd.DataFrame(
        cm,
        index=[f"true_{c}" for c in LABEL_ORDER],
        columns=[f"pred_{c}" for c in LABEL_ORDER],
    )


def _step_majority(window_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (sess, step), g in window_df.groupby(["session_uid", "step_number"]):
        rows.append({
            "session_uid": sess,
            "step_number": int(step),
            "participant_id": g["participant_id"].iloc[0],
            "procedure_id": g["procedure_id"].iloc[0],
            "vacp_score": g["vacp_score"].iloc[0],
            "n_windows": len(g),
            "y_true": g["y_true"].mode().iloc[0],
            "y_pred": g["y_pred"].mode().iloc[0],
        })
    return pd.DataFrame(rows)


def _per_participant(window_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
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

    t33, t66 = _thresholds()
    print(f"VACP thresholds: low ≤ {t33:.2f}  |  medium ≤ {t66:.2f}  |  high >")
    print(f"Feature set: {len(FEATURE_COLS)} sensor features (NO step/procedure leakage)")
    print()

    df = _load_windows(args.processed_root)
    print(f"\n  Total: {len(df)} windows")
    df = _attach_labels(df, t33, t66)
    X, y, groups, keys = _prepare(df)
    n_groups = pd.Series(groups).nunique()
    n_splits = max(2, min(args.n_splits, n_groups))

    cls_dist = dict(pd.Series(y).value_counts())
    print(f"\nTraining set: {len(X)} windows  |  {n_groups} participants  |  {n_splits}-fold CV")
    print(f"Class distribution: {cls_dist}")
    nan_pct = {c: f"{X[c].isna().mean() * 100:.1f}%" for c in FEATURE_COLS}
    print(f"NaN % per feature:")
    for c in FEATURE_COLS:
        print(f"   {c:<35} {nan_pct[c]}")

    # ---- CV ------------------------------------------------------------- #
    print("\n" + "=" * 68)
    print("GroupKFold CV (5 folds, grouped by participant)")
    print("=" * 68)
    gkf = GroupKFold(n_splits=n_splits)
    fold_metrics = []
    oof = np.empty(len(X), dtype=object)
    assigned = np.zeros(len(X), dtype=bool)

    for fold, (tr, te) in enumerate(gkf.split(X, y, groups), 1):
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
        fold_metrics.append(
            {
                "fold": fold,
                "n_train": int(len(tr)),
                "n_test": int(len(te)),
                "held_out_participants": held,
                **{k: v for k, v in mt.items() if k != "per_class"},
                "per_class": mt["per_class"],
            }
        )

    if not assigned.all():
        oof = np.where(assigned, oof, "low")

    # ---- OOF aggregates -------------------------------------------------- #
    m_win = _metrics(y, oof)
    cm_win = _confusion_df(y, oof)
    print("\n" + "=" * 68)
    print("Window-level OOF metrics")
    print("=" * 68)
    print(f"  accuracy={m_win['accuracy']:.3f}  bal_acc={m_win['balanced_accuracy']:.3f}  "
          f"F1={m_win['macro_f1']:.3f}  κ={m_win['cohen_kappa']:+.3f}")
    for cls, v in m_win["per_class"].items():
        print(f"  {cls:6s}: prec={v['precision']:.3f}  rec={v['recall']:.3f}  "
              f"f1={v['f1-score']:.3f}  n={int(v['support'])}")
    print("\nConfusion matrix:")
    print(cm_win.to_string())

    # Step-level (majority vote)
    win_pred_df = keys.copy()
    win_pred_df["y_true"] = y
    win_pred_df["y_pred"] = oof
    step_preds = _step_majority(win_pred_df)
    m_step = _metrics(step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy())
    cm_step = _confusion_df(step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy())
    print(f"\n--- Step-level (majority vote, {len(step_preds)} steps) ---")
    print(f"  accuracy={m_step['accuracy']:.3f}  bal_acc={m_step['balanced_accuracy']:.3f}  "
          f"F1={m_step['macro_f1']:.3f}  κ={m_step['cohen_kappa']:+.3f}")
    print("\nConfusion matrix:")
    print(cm_step.to_string())

    # Per-participant breakdown
    pp_df = _per_participant(win_pred_df)
    print("\n--- Per-participant balanced accuracy ---")
    print(pp_df.to_string(index=False))

    # ---- Refit + permutation importance --------------------------------- #
    print("\nRefitting on all data...")
    final_model = _new_model()
    final_model.fit(X, y)
    print("Computing permutation importance...")
    perm = permutation_importance(
        final_model, X, y,
        n_repeats=args.permutation_repeats,
        random_state=42,
        scoring="f1_macro",
        n_jobs=1,
    )
    fi_df = pd.DataFrame({
        "feature": FEATURE_COLS,
        "importance_mean": perm.importances_mean,
        "importance_std": perm.importances_std,
    }).sort_values("importance_mean", ascending=False).reset_index(drop=True)
    print("\nFeature importance:")
    print(fi_df.to_string(index=False))

    # ---- Save ------------------------------------------------------------ #
    model_path = args.models_dir / "v3_hgb_sensors_only.joblib"
    joblib.dump({
        "model": final_model,
        "feature_columns": FEATURE_COLS,
        "categorical_columns": [],
        "label_order": LABEL_ORDER,
        "label_source": "vacp_tertile_global",
        "vacp_thresholds": {"t33": t33, "t66": t66},
        "trained_on_n_windows": int(len(X)),
        "trained_on_n_participants": int(n_groups),
    }, model_path)
    print(f"\nSaved model → {model_path}")

    out = {
        "label_source": "vacp_tertile_global",
        "feature_columns": FEATURE_COLS,
        "vacp_thresholds": {"t33": t33, "t66": t66},
        "n_windows": int(len(X)),
        "n_participants": int(n_groups),
        "n_splits": int(n_splits),
        "class_distribution": {k: int(v) for k, v in cls_dist.items()},
        "fold_metrics": fold_metrics,
        "oof_window": m_win,
        "oof_step": {**m_step, "n_steps": int(len(step_preds))},
    }
    (args.models_dir / "sensors_cv_metrics.json").write_text(json.dumps(out, indent=2))
    win_pred_df.to_parquet(args.models_dir / "sensors_oof_window.parquet", index=False)
    step_preds.to_parquet(args.models_dir / "sensors_oof_step.parquet", index=False)
    fi_df.to_csv(args.models_dir / "sensors_feature_importance.csv", index=False)
    cm_win.to_csv(args.models_dir / "sensors_confusion_window.csv")
    cm_step.to_csv(args.models_dir / "sensors_confusion_step.csv")
    pp_df.to_csv(args.models_dir / "sensors_per_participant.csv", index=False)
    print(f"Saved metrics → {args.models_dir}")

    # ---- Phase target check --------------------------------------------- #
    print("\n" + "=" * 68)
    print("PLAN TARGETS:")
    print(f"  Balanced accuracy ≥ 0.65: {'✓' if m_win['balanced_accuracy'] >= 0.65 else '✗'}  "
          f"(actual: {m_win['balanced_accuracy']:.3f})")
    print(f"  Cohen's κ ≥ 0.40:         {'✓' if m_win['cohen_kappa'] >= 0.40 else '✗'}  "
          f"(actual: {m_win['cohen_kappa']:+.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
