#!/usr/bin/env python3
"""Stage 7d: Random Forest workload classifier — TUNED via Optuna.

Differences from 07c (the v4 production trainer):
  1. Optuna search over RF hyperparameters (50 trials, GroupKFold inner CV,
     macro-F1 objective). Search space mirrors the OSU LOSO RF reference
     (n_estimators 200-2000 log, max_depth 3-60, min_samples_leaf 1-30,
     min_samples_split 2-50, max_features in {sqrt, log2, None},
     bootstrap True/False, class_weight in {balanced, balanced_subsample}).
  2. A held-out test set (GroupShuffleSplit 80/20 by participant) is carved
     out BEFORE tuning, so the reported test metrics come from participants
     the tuner never saw. Optuna runs only on the 80% train pool.
  3. Outputs use the rf_tuned_* prefix and v5_rf_tuned.joblib so the
     v4 production model and rf_*.* metrics files are untouched.

Same as 07c:
  - 5 features (pupil_pcps_mean, pupil_diam_slope, blink_rate_30s,
    fixation_dur_mean_ms, fixation_dispersion_mean)
  - p_normalized k-means label construction with balance floor
  - Step 0 excluded across all 3 procedures
  - GroupKFold (participant-grouped) inside the tuner — no leakage

Outputs -> ML Algorithm/models/:
  v5_rf_tuned.joblib              tuned model + metadata + best params
  rf_tuned_cv_metrics.json        full CV + held-out test metrics
  rf_tuned_best_params.json       best Optuna trial hyperparameters
  rf_tuned_oof_window.parquet     OOF predictions (window level, 5-fold)
  rf_tuned_oof_step.parquet       OOF predictions (step level, majority vote)
  rf_tuned_feature_importance.csv RF Gini + permutation importance
  rf_tuned_confusion_window.csv   window-level confusion (5-fold OOF)
  rf_tuned_confusion_step.csv     step-level confusion (5-fold OOF)
  rf_tuned_confusion_heldout.csv  held-out test confusion
  rf_tuned_per_participant.csv    per-participant accuracy
  rf_tuned_optuna_trials.csv      every trial's params + score

Run:
  python "ML Algorithm/scripts/07d_train_rf_tuned.py"
  python "ML Algorithm/scripts/07d_train_rf_tuned.py" --n_trials 30   # faster
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import optuna
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
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import ML_ROOT, PROCEDURE_ID_TO_SLUG, PROCESSED_ROOT  # noqa: E402

# Silence Optuna's per-trial INFO logs; we print our own progress line.
optuna.logging.set_verbosity(optuna.logging.WARNING)

# --------------------------------------------------------------------------- #
# Feature contract — identical to 07c                                         #
# --------------------------------------------------------------------------- #

FEATURE_COLS = [
    "pupil_pcps_mean",
    "pupil_diam_slope",
    "blink_rate_30s",
    "fixation_dur_mean_ms",
    "fixation_dispersion_mean",
]
GROUP_COL = "participant_id"
LABEL_ORDER = ["low", "high"]

PROC_LABEL_TO_ID = {
    "Centrifuge task": 1,
    "Column Flushing task": 2,
    "Pressure Testing task": 3,
}

RANDOM_STATE = 42

# --------------------------------------------------------------------------- #
# Y label construction — identical to 07c                                     #
# --------------------------------------------------------------------------- #

def _load_step_summary() -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for slug in ("centrifuge", "column_flushing", "pressure_testing"):
        p = PROCESSED_ROOT / "Y labels" / f"{slug}_vacp_workload.xlsx"
        s = pd.read_excel(p, sheet_name="Step Summary")
        s["procedure_slug"] = slug
        s["procedure_id"] = s["Procedure"].map(PROC_LABEL_TO_ID)
        rows.append(s)
    return pd.concat(rows, ignore_index=True)


def _build_label_table(step_summary: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    MIN_CLASS_SIZE = 7
    train = step_summary[step_summary["Step ID"] > 0].copy().reset_index(drop=True)
    sorted_vals = np.sort(train["p_normalized"].to_numpy())
    n = len(sorted_vals)

    vals = train[["p_normalized"]].to_numpy()
    km = KMeans(n_clusters=2, n_init=50, random_state=RANDOM_STATE).fit(vals)
    centers = sorted(km.cluster_centers_.flatten().tolist())
    km_boundary = (centers[0] + centers[1]) / 2
    km_low = int(np.sum(sorted_vals <= km_boundary))
    km_high = n - km_low

    candidates: list[tuple[float, int, int, float]] = []
    for i in range(n - 1):
        mid = (sorted_vals[i] + sorted_vals[i + 1]) / 2.0
        gap = sorted_vals[i + 1] - sorted_vals[i]
        n_low = i + 1
        n_high = n - n_low
        balance_penalty = -1.0 if (n_low < MIN_CLASS_SIZE or n_high < MIN_CLASS_SIZE) else 0.0
        candidates.append((mid, n_low, n_high, gap + balance_penalty))
    eligible = [c for c in candidates if c[1] >= MIN_CLASS_SIZE and c[2] >= MIN_CLASS_SIZE]
    if eligible:
        chosen = max(eligible, key=lambda c: c[3])
        chosen_boundary, chosen_low, chosen_high, chosen_gap = chosen
        method = "largest_gap_with_balance_floor"
    else:
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
# Window loading — identical to 07c                                           #
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
    key = step_labels.rename(columns={"Step ID": "step_number"})[
        ["procedure_id", "step_number", "p_normalized", "workload_label"]
    ]
    windows_clean = windows.drop(columns=[c for c in ("workload_label", "p_normalized") if c in windows.columns])
    out = windows_clean.merge(key, on=["procedure_id", "step_number"], how="left")
    n_total = len(out)
    out = out[out["workload_label"].notna()].copy()
    print(f"  Dropped {n_total - len(out)} windows that fell on step 0 (excluded)")
    return out


def _prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, pd.DataFrame]:
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise KeyError(f"X_window.parquet missing required feature cols: {missing}")
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
    keys = df[["session_uid", "step_number", "procedure_id", "participant_id", "p_normalized"]].reset_index(drop=True)
    return X.reset_index(drop=True), y, groups, keys


# --------------------------------------------------------------------------- #
# Model factory — accepts hyperparameters from Optuna                         #
# --------------------------------------------------------------------------- #

def _new_model(params: dict) -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("rf", RandomForestClassifier(
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            min_samples_split=params["min_samples_split"],
            min_samples_leaf=params["min_samples_leaf"],
            max_features=params["max_features"],
            bootstrap=params["bootstrap"],
            class_weight=params["class_weight"],
            n_jobs=-1,
            random_state=RANDOM_STATE,
        )),
    ])


# --------------------------------------------------------------------------- #
# Metrics helpers — identical to 07c                                          #
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
    return pd.DataFrame(cm, index=[f"true_{c}" for c in LABEL_ORDER],
                        columns=[f"pred_{c}" for c in LABEL_ORDER])


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
# Optuna objective                                                            #
# --------------------------------------------------------------------------- #

def _build_objective(X_train: pd.DataFrame, y_train: np.ndarray,
                     groups_train: np.ndarray, n_splits: int):
    """Closure: each trial runs GroupKFold on the train pool and returns mean macro-F1."""
    gkf = GroupKFold(n_splits=n_splits)
    folds = list(gkf.split(X_train, y_train, groups_train))

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 200, 2000, log=True),
            "max_depth": trial.suggest_int("max_depth", 3, 60),
            "min_samples_split": trial.suggest_int("min_samples_split", 2, 50),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 1, 30),
            "max_features": trial.suggest_categorical("max_features", ["sqrt", "log2", None]),
            "bootstrap": trial.suggest_categorical("bootstrap", [True, False]),
            "class_weight": trial.suggest_categorical("class_weight", ["balanced", "balanced_subsample"]),
        }
        fold_f1: list[float] = []
        fold_bal: list[float] = []
        for tr_i, va_i in folds:
            pipe = _new_model(params)
            pipe.fit(X_train.iloc[tr_i], y_train[tr_i])
            pred = pipe.predict(X_train.iloc[va_i])
            fold_f1.append(f1_score(y_train[va_i], pred, labels=LABEL_ORDER,
                                    average="macro", zero_division=0))
            fold_bal.append(balanced_accuracy_score(y_train[va_i], pred))
        trial.set_user_attr("mean_balanced_acc", float(np.mean(fold_bal)))
        return float(np.mean(fold_f1))

    return objective


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed_root", type=Path, default=PROCESSED_ROOT)
    ap.add_argument("--models_dir", type=Path, default=ML_ROOT / "models")
    ap.add_argument("--n_splits", type=int, default=5)
    ap.add_argument("--n_trials", type=int, default=50)
    ap.add_argument("--test_size", type=float, default=0.20,
                    help="Fraction of PARTICIPANTS held out for final test")
    ap.add_argument("--permutation_repeats", type=int, default=10)
    args = ap.parse_args(argv)
    args.models_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. Y labels ---------------------------------------------------- #
    print("=" * 70)
    print("Step 1: Cluster p_normalized into 2 classes (low / high)")
    print("=" * 70)
    summary = _load_step_summary()
    step_labels, meta = _build_label_table(summary)
    print(f"  Chosen boundary: low <= {meta['chosen_boundary']}  |  high >")
    print(f"  Step-level distribution: {meta['class_distribution_step_level']}")

    # ---- 2. Windows + labels ------------------------------------------- #
    print("\n" + "=" * 70)
    print("Step 2: Load X_window.parquet for all 3 procedures")
    print("=" * 70)
    windows = _load_windows()
    print(f"  Total windows: {len(windows)}")
    windows = _attach_labels(windows, step_labels)

    # ---- 3. Prepare ---------------------------------------------------- #
    X, y, groups, keys = _prepare(windows)
    n_groups = pd.Series(groups).nunique()
    n_splits = max(2, min(args.n_splits, n_groups - 1))
    cls_dist = dict(pd.Series(y).value_counts().sort_index())
    print(f"\n  After filtering: {len(X)} windows  |  {n_groups} participants")
    print(f"  Window-level class distribution: {cls_dist}")

    # ---- 4. Held-out test split (by participant) ----------------------- #
    print("\n" + "=" * 70)
    print(f"Step 3: Hold out {args.test_size*100:.0f}% of participants for final test")
    print("=" * 70)
    gss = GroupShuffleSplit(n_splits=1, test_size=args.test_size, random_state=RANDOM_STATE)
    train_idx, test_idx = next(gss.split(X, y, groups))
    X_tr_pool, X_test = X.iloc[train_idx].reset_index(drop=True), X.iloc[test_idx].reset_index(drop=True)
    y_tr_pool, y_test = y[train_idx], y[test_idx]
    groups_tr_pool, groups_test = groups[train_idx], groups[test_idx]
    keys_tr_pool = keys.iloc[train_idx].reset_index(drop=True)
    keys_test = keys.iloc[test_idx].reset_index(drop=True)
    tune_groups = sorted(set(groups_tr_pool))
    held_groups = sorted(set(groups_test))
    print(f"  Tune pool : {len(X_tr_pool)} windows | {len(tune_groups)} participants -> {tune_groups}")
    print(f"  Held-out  : {len(X_test)} windows | {len(held_groups)} participants -> {held_groups}")
    n_splits_tune = max(2, min(args.n_splits, len(tune_groups) - 1))

    # ---- 5. Optuna ----------------------------------------------------- #
    print("\n" + "=" * 70)
    print(f"Step 4: Optuna hyperparameter search ({args.n_trials} trials, "
          f"{n_splits_tune}-fold GroupKFold on tune pool)")
    print("=" * 70)
    objective = _build_objective(X_tr_pool, y_tr_pool, groups_tr_pool, n_splits_tune)
    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=RANDOM_STATE))

    def _trial_callback(study: optuna.Study, trial: optuna.trial.FrozenTrial) -> None:
        print(f"  Trial {trial.number+1:>3d}/{args.n_trials}  "
              f"macro_f1={trial.value:.4f}  bal_acc={trial.user_attrs.get('mean_balanced_acc', float('nan')):.4f}  "
              f"best_so_far={study.best_value:.4f}")

    study.optimize(objective, n_trials=args.n_trials, callbacks=[_trial_callback],
                   show_progress_bar=False)
    best_params = dict(study.best_params)
    print(f"\n  Best macro-F1 (CV mean on tune pool): {study.best_value:.4f}")
    print(f"  Best params: {best_params}")

    # ---- 6. 5-fold OOF on FULL data with best params (apples-to-apples vs v4) ---- #
    print("\n" + "=" * 70)
    print(f"Step 5: Re-run 5-fold GroupKFold OOF on ALL data with best params "
          f"(for direct comparison vs v4)")
    print("=" * 70)
    n_splits_full = max(2, min(args.n_splits, n_groups))
    gkf_full = GroupKFold(n_splits=n_splits_full)
    fold_metrics: list[dict] = []
    oof = np.empty(len(X), dtype=object)
    assigned = np.zeros(len(X), dtype=bool)
    for fold, (tr, te) in enumerate(gkf_full.split(X, y, groups), start=1):
        m = _new_model(best_params)
        m.fit(X.iloc[tr], y[tr])
        pred = m.predict(X.iloc[te])
        oof[te] = pred
        assigned[te] = True
        mt = _metrics(y[te], pred)
        held = sorted(set(groups[te]))
        print(f"  Fold {fold}: acc={mt['accuracy']:.3f}  bal_acc={mt['balanced_accuracy']:.3f}  "
              f"macro_f1={mt['macro_f1']:.3f}  k={mt['cohen_kappa']:+.3f}  held-out={held}")
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

    m_win = _metrics(y, oof)
    cm_win = _confusion_df(y, oof)
    print(f"\n[5-fold OOF / Window level]")
    print(f"  accuracy = {m_win['accuracy']:.3f}  bal_acc = {m_win['balanced_accuracy']:.3f}  "
          f"macro_f1 = {m_win['macro_f1']:.3f}  k = {m_win['cohen_kappa']:+.3f}")

    win_pred_df = keys.copy()
    win_pred_df["y_true"] = y
    win_pred_df["y_pred"] = oof
    step_preds = _step_majority_vote(win_pred_df)
    m_step = _metrics(step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy())
    cm_step = _confusion_df(step_preds["y_true"].to_numpy(), step_preds["y_pred"].to_numpy())
    print(f"[5-fold OOF / Step level ({len(step_preds)} steps)]")
    print(f"  accuracy = {m_step['accuracy']:.3f}  bal_acc = {m_step['balanced_accuracy']:.3f}  "
          f"macro_f1 = {m_step['macro_f1']:.3f}  k = {m_step['cohen_kappa']:+.3f}")

    # ---- 7. Held-out test eval ----------------------------------------- #
    print("\n" + "=" * 70)
    print("Step 6: Train on full tune pool, evaluate on held-out test set")
    print("=" * 70)
    held_model = _new_model(best_params)
    held_model.fit(X_tr_pool, y_tr_pool)
    test_pred = held_model.predict(X_test)
    m_held = _metrics(y_test, test_pred)
    cm_held = _confusion_df(y_test, test_pred)
    print(f"  accuracy = {m_held['accuracy']:.3f}  bal_acc = {m_held['balanced_accuracy']:.3f}  "
          f"macro_f1 = {m_held['macro_f1']:.3f}  k = {m_held['cohen_kappa']:+.3f}")
    print("  Confusion (held-out):")
    print(cm_held.to_string())

    # Step-level confusion on held-out too (for completeness)
    held_keys_pred = keys_test.copy()
    held_keys_pred["y_true"] = y_test
    held_keys_pred["y_pred"] = test_pred
    held_step_preds = _step_majority_vote(held_keys_pred)
    m_held_step = _metrics(held_step_preds["y_true"].to_numpy(), held_step_preds["y_pred"].to_numpy())

    # ---- 8. Refit on ALL data + importance ----------------------------- #
    print("\n" + "=" * 70)
    print("Step 7: Refit on ALL data + permutation importance")
    print("=" * 70)
    final_model = _new_model(best_params)
    final_model.fit(X, y)
    rf = final_model.named_steps["rf"]
    builtin_imp = pd.DataFrame({"feature": FEATURE_COLS, "rf_gini_importance": rf.feature_importances_})
    perm = permutation_importance(final_model, X, y, n_repeats=args.permutation_repeats,
                                  random_state=RANDOM_STATE, scoring="f1_macro", n_jobs=-1)
    fi_df = builtin_imp.copy()
    fi_df["permutation_importance_mean"] = perm.importances_mean
    fi_df["permutation_importance_std"] = perm.importances_std
    fi_df = fi_df.sort_values("permutation_importance_mean", ascending=False).reset_index(drop=True)
    print(fi_df.round(4).to_string(index=False))

    pp_df = _per_participant(win_pred_df)

    # ---- 9. Save ------------------------------------------------------- #
    model_path = args.models_dir / "v5_rf_tuned.joblib"
    joblib.dump({
        "model": final_model,
        "feature_columns": FEATURE_COLS,
        "categorical_columns": [],
        "label_order": LABEL_ORDER,
        "label_source": "p_normalized_kmeans3",
        "label_meta": meta,
        "best_params": best_params,
        "n_trials": int(args.n_trials),
        "trained_on_n_windows": int(len(X)),
        "trained_on_n_participants": int(n_groups),
    }, model_path)
    print(f"\nSaved model -> {model_path}")

    out = {
        "label_source": "p_normalized_kmeans3",
        "label_meta": meta,
        "feature_columns": FEATURE_COLS,
        "best_params": best_params,
        "n_trials": int(args.n_trials),
        "optuna_best_macro_f1_cv": float(study.best_value),
        "n_windows": int(len(X)),
        "n_participants": int(n_groups),
        "n_splits": int(n_splits_full),
        "class_distribution_window": {k: int(v) for k, v in cls_dist.items()},
        "fold_metrics": fold_metrics,
        "oof_window": m_win,
        "oof_step": {**m_step, "n_steps": int(len(step_preds))},
        "held_out_test": {
            "tune_participants": tune_groups,
            "held_out_participants": held_groups,
            "n_windows": int(len(X_test)),
            "window_level": m_held,
            "step_level": {**m_held_step, "n_steps": int(len(held_step_preds))},
        },
    }
    (args.models_dir / "rf_tuned_cv_metrics.json").write_text(json.dumps(out, indent=2))
    (args.models_dir / "rf_tuned_best_params.json").write_text(json.dumps(best_params, indent=2))
    win_pred_df.to_parquet(args.models_dir / "rf_tuned_oof_window.parquet", index=False)
    step_preds.to_parquet(args.models_dir / "rf_tuned_oof_step.parquet", index=False)
    fi_df.to_csv(args.models_dir / "rf_tuned_feature_importance.csv", index=False)
    cm_win.to_csv(args.models_dir / "rf_tuned_confusion_window.csv")
    cm_step.to_csv(args.models_dir / "rf_tuned_confusion_step.csv")
    cm_held.to_csv(args.models_dir / "rf_tuned_confusion_heldout.csv")
    pp_df.to_csv(args.models_dir / "rf_tuned_per_participant.csv", index=False)

    trials_df = study.trials_dataframe()
    trials_df.to_csv(args.models_dir / "rf_tuned_optuna_trials.csv", index=False)
    print(f"Saved metrics/outputs -> {args.models_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
