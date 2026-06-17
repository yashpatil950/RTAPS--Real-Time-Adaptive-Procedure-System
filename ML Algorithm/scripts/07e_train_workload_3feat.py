#!/usr/bin/env python3
"""Stage 7e: robust workload classifier — drops the train/serve-skewed
fixation feature and uses a smooth, calibrated linear model.

WHY THIS EXISTS
---------------
The v5 tuned Random Forest (07d) predicted "high" essentially 100% of the
time in live serving. Root cause (verified by decision-surface probing):

  * `fixation_dur_mean_ms` was the model's dominant feature (~42% Gini
    importance) but suffered a severe TRAIN/SERVE SKEW. Training windows
    (offline Pupil-player export) had fixation durations of 100-211 ms
    (median 134). The LIVE Online Fixation Detector rails every fixation at
    its "Maximum Duration" (~300 ms), so the live feature sits permanently at
    ~302 ms — above the training maximum, with no variance. A dominant
    feature pinned at a constant beyond its training range votes one class
    (high) forever.
  * The RF was also overfit (bootstrap=False, depth 18, min_samples_leaf=1),
    emitting hard 0/1 probabilities that the workload smoother could never
    move off "high".

Crucially, dropping fixation costs almost nothing in cross-participant skill
(leave-one-participant-out kappa 0.045 -> 0.047 for RF) because the feature
carried bias, not generalizable signal. Replacing the overfit RF with a
class-balanced logistic regression on the three baseline-COMPARABLE features
RAISES held-out kappa to ~0.16 and — because pcps is baseline-normalized and
blink_rate is a simple count — there is no train/serve skew left to rail the
output. The live prediction now responds to physiology instead of being
pinned.

FEATURES (3, all comparable between training and live serving):
  pupil_pcps_mean   — percent change in pupil size vs the per-session baseline
  pupil_diam_slope  — pupil dilation trend within the window
  blink_rate_30s    — blink count in the trailing 30 s

LABELS: identical construction to 07c/07d (p_normalized split at the
largest gap with a per-class balance floor), so this model is directly
comparable to the prior versions.

Outputs -> ML Algorithm/models/:
  v6_logreg_3feat.joblib            model + metadata (predictor-compatible dict)
  logreg_3feat_cv_metrics.json      LOSO + 5-fold group CV metrics
  logreg_3feat_per_participant.csv  per-participant held-out accuracy

Run:
  python "ML Algorithm/scripts/07e_train_workload_3feat.py"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (balanced_accuracy_score, classification_report,
                             cohen_kappa_score, confusion_matrix, f1_score)
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import ML_ROOT, PROCEDURE_ID_TO_SLUG, PROCESSED_ROOT  # noqa: E402

FEATURE_COLS = ["pupil_pcps_mean", "pupil_diam_slope", "blink_rate_30s"]
GROUP_COL = "participant_id"
LABEL_ORDER = ["low", "high"]
PROC_LABEL_TO_ID = {"Centrifuge task": 1, "Column Flushing task": 2, "Pressure Testing task": 3}
RANDOM_STATE = 42


# ---- label construction (same as 07c/07d) -------------------------------- #
def _load_step_summary() -> pd.DataFrame:
    rows = []
    for slug in ("centrifuge", "column_flushing", "pressure_testing"):
        s = pd.read_excel(PROCESSED_ROOT / "Y labels" / f"{slug}_vacp_workload.xlsx",
                          sheet_name="Step Summary")
        s["procedure_id"] = s["Procedure"].map(PROC_LABEL_TO_ID)
        rows.append(s)
    return pd.concat(rows, ignore_index=True)


def _build_label_table(step_summary: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    MIN_CLASS_SIZE = 7
    train = step_summary[step_summary["Step ID"] > 0].copy().reset_index(drop=True)
    sv = np.sort(train["p_normalized"].to_numpy())
    n = len(sv)
    candidates = []
    for i in range(n - 1):
        mid = (sv[i] + sv[i + 1]) / 2.0
        gap = sv[i + 1] - sv[i]
        nl, nh = i + 1, n - (i + 1)
        pen = -1.0 if (nl < MIN_CLASS_SIZE or nh < MIN_CLASS_SIZE) else 0.0
        candidates.append((mid, nl, nh, gap + pen))
    eligible = [c for c in candidates if c[1] >= MIN_CLASS_SIZE and c[2] >= MIN_CLASS_SIZE]
    chosen = max(eligible, key=lambda c: c[3])
    bnd = chosen[0]
    train["workload_label"] = ["high" if v > bnd else "low" for v in train["p_normalized"]]
    meta = {
        "method": "largest_gap_with_balance_floor",
        "chosen_boundary": round(float(bnd), 4),
        "n_steps_total": int(n),
        "class_distribution_step_level": train["workload_label"].value_counts().to_dict(),
    }
    return train.rename(columns={"Step ID": "step_number"})[
        ["procedure_id", "step_number", "p_normalized", "workload_label"]], meta


def _load_windows() -> pd.DataFrame:
    frames = []
    for slug in PROCEDURE_ID_TO_SLUG.values():
        p = PROCESSED_ROOT / slug / "X_window.parquet"
        df = pd.read_parquet(p)
        frames.append(df)
        print(f"  {slug}: {len(df)} windows | {df['participant_id'].nunique()} participants")
    return pd.concat(frames, ignore_index=True)


def _prepare(windows: pd.DataFrame, labels: pd.DataFrame):
    wc = windows.drop(columns=[c for c in ("workload_label", "p_normalized") if c in windows.columns])
    out = wc.merge(labels, on=["procedure_id", "step_number"], how="left")
    out = out[out["workload_label"].notna()].copy()
    mask = (out["valid"].astype(bool) & out["workload_label"].isin(LABEL_ORDER)
            & out[GROUP_COL].notna() & (out[GROUP_COL].astype(str).str.len() > 0))
    out = out.loc[mask].copy()
    X = out[FEATURE_COLS].reset_index(drop=True)
    y = out["workload_label"].astype(str).to_numpy()
    groups = out[GROUP_COL].astype(str).to_numpy()
    return X, y, groups


def _new_model() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("lr", LogisticRegression(class_weight="balanced", max_iter=2000,
                                  random_state=RANDOM_STATE)),
    ])


def _metrics(yt, yp) -> dict:
    rep = classification_report(yt, yp, labels=LABEL_ORDER, zero_division=0, output_dict=True)
    return {
        "accuracy": float((yt == yp).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(yt, yp)),
        "macro_f1": float(f1_score(yt, yp, labels=LABEL_ORDER, average="macro", zero_division=0)),
        "cohen_kappa": float(cohen_kappa_score(yt, yp, labels=LABEL_ORDER)),
        "per_class": {c: rep[c] for c in LABEL_ORDER},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models_dir", type=Path, default=ML_ROOT / "models")
    args = ap.parse_args(argv)
    args.models_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Step 1: Build labels (p_normalized, largest-gap split)")
    print("=" * 70)
    labels, meta = _build_label_table(_load_step_summary())
    print(f"  boundary low<= {meta['chosen_boundary']} <high   "
          f"step-level: {meta['class_distribution_step_level']}")

    print("\n" + "=" * 70)
    print("Step 2: Load windows + attach labels")
    print("=" * 70)
    X, y, groups = _prepare(_load_windows(), labels)
    n_groups = pd.Series(groups).nunique()
    print(f"  {len(X)} windows | {n_groups} participants | "
          f"class dist {dict(pd.Series(y).value_counts())}")

    # ---- Leave-One-Participant-Out (the honest serving estimate) ---------- #
    print("\n" + "=" * 70)
    print("Step 3: Leave-One-Participant-Out CV")
    print("=" * 70)
    logo = LeaveOneGroupOut()
    oof = np.empty(len(X), dtype=object)
    per_part = []
    for tr, te in logo.split(X, y, groups):
        m = _new_model(); m.fit(X.iloc[tr], y[tr])
        pred = m.predict(X.iloc[te]); oof[te] = pred
        pid = groups[te][0]
        mt = _metrics(y[te], pred)
        per_part.append({"participant_id": pid, "n_windows": int(te.sum() if hasattr(te, "sum") else len(te)),
                         "balanced_accuracy": mt["balanced_accuracy"], "macro_f1": mt["macro_f1"],
                         "cohen_kappa": mt["cohen_kappa"]})
    m_loso = _metrics(y, oof)
    print(f"  pooled LOSO: bal_acc={m_loso['balanced_accuracy']:.3f}  "
          f"macro_f1={m_loso['macro_f1']:.3f}  kappa={m_loso['cohen_kappa']:+.3f}")
    pp_df = pd.DataFrame(per_part).sort_values("balanced_accuracy", ascending=False)
    n_above = int((pp_df["balanced_accuracy"] > 0.5).sum())
    print(f"  {n_above}/{len(pp_df)} participants above chance (bal_acc>0.5)")

    # ---- 5-fold group CV (comparable to v4/v5 reporting) ------------------ #
    gkf = GroupKFold(n_splits=min(5, n_groups))
    oof5 = np.empty(len(X), dtype=object)
    for tr, te in gkf.split(X, y, groups):
        m = _new_model(); m.fit(X.iloc[tr], y[tr]); oof5[te] = m.predict(X.iloc[te])
    m_5fold = _metrics(y, oof5)
    cm = confusion_matrix(y, oof5, labels=LABEL_ORDER)
    print(f"  5-fold group CV: bal_acc={m_5fold['balanced_accuracy']:.3f}  "
          f"macro_f1={m_5fold['macro_f1']:.3f}  kappa={m_5fold['cohen_kappa']:+.3f}")

    # ---- Fit final model on ALL data -------------------------------------- #
    print("\n" + "=" * 70)
    print("Step 4: Fit final model on all data + save")
    print("=" * 70)
    final = _new_model(); final.fit(X, y)
    coef = final.named_steps["lr"].coef_[0]
    cls = list(final.named_steps["lr"].classes_)
    print(f"  coefficients (positive => pushes toward '{cls[1]}'):")
    for f, c in zip(FEATURE_COLS, coef):
        print(f"     {f:20s} {c:+.4f}")

    model_path = args.models_dir / "v6_logreg_3feat.joblib"
    joblib.dump({
        "model": final,
        "feature_columns": FEATURE_COLS,
        "categorical_columns": [],
        "label_order": LABEL_ORDER,
        "label_source": "p_normalized_largest_gap",
        "label_meta": meta,
        "model_kind": "logreg_class_balanced",
        "dropped_features": ["fixation_dur_mean_ms"],
        "drop_reason": "train/serve skew (live Online Fixation Detector rails at ~300ms vs training 100-211ms); "
                       "was dominant feature causing always-high; ~0 contribution to LOSO kappa",
        "trained_on_n_windows": int(len(X)),
        "trained_on_n_participants": int(n_groups),
    }, model_path)
    print(f"  Saved -> {model_path}")

    out = {
        "model_kind": "logreg_class_balanced",
        "feature_columns": FEATURE_COLS,
        "label_source": "p_normalized_largest_gap",
        "label_meta": meta,
        "n_windows": int(len(X)),
        "n_participants": int(n_groups),
        "class_distribution_window": {k: int(v) for k, v in pd.Series(y).value_counts().items()},
        "loso": {k: v for k, v in m_loso.items() if k != "per_class"},
        "five_fold_group": {k: v for k, v in m_5fold.items() if k != "per_class"},
        "confusion_5fold": {"labels": LABEL_ORDER, "matrix": cm.tolist()},
        "coefficients": {f: float(c) for f, c in zip(FEATURE_COLS, coef)},
        "coef_positive_class": cls[1],
        "participants_above_chance": f"{n_above}/{len(pp_df)}",
    }
    (args.models_dir / "logreg_3feat_cv_metrics.json").write_text(json.dumps(out, indent=2))
    pp_df.to_csv(args.models_dir / "logreg_3feat_per_participant.csv", index=False)
    print(f"  Saved metrics -> {args.models_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
