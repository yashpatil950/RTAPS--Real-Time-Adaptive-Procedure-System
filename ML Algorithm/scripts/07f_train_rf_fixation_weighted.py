#!/usr/bin/env python3
"""Stage 7f: Random Forest workload classifier with fixation DOWN-WEIGHTED to 15%.

GOAL
----
Keep `fixation_dur_mean_ms` as a model input (per request) but limit its
influence to ~15% of the decision, instead of the ~42% Gini importance it held
in the v5 tuned RF — where, because the live Online Fixation Detector rails
every fixation at ~300 ms (a constant above the 100-211 ms training range), it
forced "high" on essentially every live window.

WHY A BLEND (not a single RF)
-----------------------------
Feature importance in a single Random Forest is emergent, not a knob: capping
`max_features` only drags fixation from 42% to ~36% and the live prediction
still rails to 100% "high" (a railed constant nudges every window over the
line regardless of its weight). The only way to give fixation an EXACT, bounded
share of the decision is to blend two models with fixed weights:

    P(high) = 0.85 * P_base(pupil_pcps, pupil_slope, blink)   # the 85%
            + 0.15 * P_fix(fixation_dur_mean_ms)              # the 15%

Both components are Random Forests, combined with sklearn's standard
`VotingClassifier(voting="soft", weights=[0.85, 0.15])` — so it stays a tunable
RF model and loads through the existing predictor with no custom class. The
15% is guaranteed by construction; fixation can lean the result but never
dominate, so the output tracks pupil + blink and stays responsive.

FEATURE CONTRACT (4, order matters — the blend selects columns by position):
    [0] pupil_pcps_mean
    [1] pupil_diam_slope
    [2] blink_rate_30s
    [3] fixation_dur_mean_ms   <- routed only to the 15% sub-model

Labels: same p_normalized largest-gap construction as 07c/07d/07e.

Outputs -> ML Algorithm/models/:
  v7_rf_fixation15.joblib          model + metadata (predictor-compatible dict)
  rf_fixation15_cv_metrics.json    LOSO + live-responsiveness diagnostics

Run:
  python "ML Algorithm/scripts/07f_train_rf_fixation_weighted.py"
  python "ML Algorithm/scripts/07f_train_rf_fixation_weighted.py" --fix_weight 0.15
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (balanced_accuracy_score, cohen_kappa_score,
                             f1_score)
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import ML_ROOT, PROCEDURE_ID_TO_SLUG, PROCESSED_ROOT  # noqa: E402

FEATURE_COLS = ["pupil_pcps_mean", "pupil_diam_slope", "blink_rate_30s", "fixation_dur_mean_ms"]
BASE_IDX = [0, 1, 2]          # pupil + blink  -> the (1 - fix_weight) share
FIX_IDX = [3]                 # fixation       -> the fix_weight share
LABEL_ORDER = ["low", "high"]
PROC_LABEL_TO_ID = {"Centrifuge task": 1, "Column Flushing task": 2, "Pressure Testing task": 3}
RANDOM_STATE = 42


def _load_step_summary() -> pd.DataFrame:
    rows = []
    for slug in ("centrifuge", "column_flushing", "pressure_testing"):
        s = pd.read_excel(PROCESSED_ROOT / "Y labels" / f"{slug}_vacp_workload.xlsx", sheet_name="Step Summary")
        s["procedure_id"] = s["Procedure"].map(PROC_LABEL_TO_ID)
        rows.append(s)
    return pd.concat(rows, ignore_index=True)


def _build_label_table(step_summary: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    MIN_CLASS_SIZE = 7
    train = step_summary[step_summary["Step ID"] > 0].copy().reset_index(drop=True)
    sv = np.sort(train["p_normalized"].to_numpy()); n = len(sv); cand = []
    for i in range(n - 1):
        nl, nh = i + 1, n - (i + 1)
        pen = -1.0 if (nl < MIN_CLASS_SIZE or nh < MIN_CLASS_SIZE) else 0.0
        # tuple = (boundary, n_low, n_high, gap_score)
        cand.append(((sv[i] + sv[i + 1]) / 2, nl, nh, sv[i + 1] - sv[i] + pen))
    bnd = max([c for c in cand if c[1] >= MIN_CLASS_SIZE and c[2] >= MIN_CLASS_SIZE], key=lambda c: c[3])[0]
    train["workload_label"] = ["high" if v > bnd else "low" for v in train["p_normalized"]]
    meta = {"method": "largest_gap_with_balance_floor", "chosen_boundary": round(float(bnd), 4),
            "class_distribution_step_level": train["workload_label"].value_counts().to_dict()}
    return train.rename(columns={"Step ID": "step_number"})[["procedure_id", "step_number", "workload_label"]], meta


def _prepare():
    labels, meta = _build_label_table(_load_step_summary())
    frames = []
    for slug in PROCEDURE_ID_TO_SLUG.values():
        df = pd.read_parquet(PROCESSED_ROOT / slug / "X_window.parquet")
        frames.append(df); print(f"  {slug}: {len(df)} windows | {df['participant_id'].nunique()} participants")
    w = pd.concat(frames, ignore_index=True)
    w = w.drop(columns=[c for c in ("workload_label",) if c in w.columns]).merge(labels, on=["procedure_id", "step_number"], how="left")
    m = (w["valid"].astype(bool) & w["workload_label"].isin(LABEL_ORDER)
         & w["participant_id"].notna() & (w["participant_id"].astype(str).str.len() > 0))
    w = w.loc[m].copy()
    return w[FEATURE_COLS].reset_index(drop=True), w["workload_label"].astype(str).to_numpy(), \
        w["participant_id"].astype(str).to_numpy(), meta


def _rf(idx, depth, leaf, n_est=400):
    """Column-selecting RF pipeline. `idx` are positional column indices."""
    return Pipeline([
        ("sel", ColumnTransformer([("keep", "passthrough", idx)], remainder="drop")),
        ("imp", SimpleImputer(strategy="median")),
        ("rf", RandomForestClassifier(n_estimators=n_est, max_depth=depth, min_samples_leaf=leaf,
                                      max_features="sqrt", bootstrap=True, class_weight="balanced",
                                      random_state=RANDOM_STATE, n_jobs=-1)),
    ])


def _blend(fix_weight: float) -> VotingClassifier:
    # base = regularized RF on pupil+blink (validated responsive config);
    # fix  = shallow RF on fixation alone. Soft-vote with fixed weights.
    base = _rf(BASE_IDX, depth=6, leaf=40)
    fixm = _rf(FIX_IDX, depth=4, leaf=50, n_est=300)
    return VotingClassifier([("base", base), ("fix", fixm)], voting="soft",
                            weights=[1.0 - fix_weight, fix_weight])


def _live_responsiveness(model) -> dict:
    """Sweep pupil+blink with fixation pinned at the live ~302 ms rail; report
    whether the output varies (not stuck at 'high')."""
    rows = [{"pupil_pcps_mean": pc, "pupil_diam_slope": sl, "blink_rate_30s": float(bl),
             "fixation_dur_mean_ms": 302.0}
            for pc in np.linspace(-0.3, 1.0, 14) for bl in range(0, 22, 3) for sl in (-0.05, 0.0, 0.05)]
    G = pd.DataFrame(rows)[FEATURE_COLS]
    pr = model.predict_proba(G)[:, list(model.classes_).index("high")]
    return {"frac_high": float((pr > 0.5).mean()), "p_high_min": float(pr.min()),
            "p_high_mean": float(pr.mean()), "p_high_max": float(pr.max())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models_dir", type=Path, default=ML_ROOT / "models")
    ap.add_argument("--fix_weight", type=float, default=0.15,
                    help="Fraction of the decision assigned to fixation (default 0.15)")
    args = ap.parse_args(argv)
    args.models_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70); print("Load windows + labels"); print("=" * 70)
    X, y, g, meta = _prepare()
    print(f"  {len(X)} windows | {pd.Series(g).nunique()} participants | "
          f"class dist {dict(pd.Series(y).value_counts())}")

    print("\n" + "=" * 70)
    print(f"Leave-One-Participant-Out CV (fixation weight = {args.fix_weight:.0%})")
    print("=" * 70)
    logo = LeaveOneGroupOut()
    oof = np.empty(len(X), dtype=object)
    for tr, te in logo.split(X, y, g):
        m = _blend(args.fix_weight); m.fit(X.iloc[tr], y[tr]); oof[te] = m.predict(X.iloc[te])
    k = cohen_kappa_score(y, oof, labels=LABEL_ORDER)
    f = f1_score(y, oof, labels=LABEL_ORDER, average="macro")
    b = balanced_accuracy_score(y, oof)
    print(f"  LOSO kappa={k:+.3f}  macro_f1={f:.3f}  bal_acc={b:.3f}")

    print("\n" + "=" * 70); print("Fit final blend on all data + live responsiveness check"); print("=" * 70)
    final = _blend(args.fix_weight); final.fit(X, y)
    resp = _live_responsiveness(final)
    print(f"  live (fixation pinned @302ms): frac_high={resp['frac_high']:.1%}  "
          f"p_high {resp['p_high_min']:.2f}..{resp['p_high_mean']:.2f}..{resp['p_high_max']:.2f}")
    print(f"  (v5 was frac_high=100% / p_high=1.00 — i.e. always high)")

    pct = int(round(args.fix_weight * 100))
    model_path = args.models_dir / f"v7_rf_fixation{pct}.joblib"
    joblib.dump({
        "model": final,
        "feature_columns": FEATURE_COLS,
        "categorical_columns": [],
        "label_order": LABEL_ORDER,
        "label_source": "p_normalized_largest_gap",
        "label_meta": meta,
        "model_kind": "soft_voting_rf_blend",
        "fixation_weight": float(args.fix_weight),
        "blend": {"base_features": [FEATURE_COLS[i] for i in BASE_IDX],
                  "fix_features": [FEATURE_COLS[i] for i in FIX_IDX],
                  "weights": [1.0 - args.fix_weight, args.fix_weight]},
        "trained_on_n_windows": int(len(X)),
        "trained_on_n_participants": int(pd.Series(g).nunique()),
    }, model_path)
    print(f"\n  Saved -> {model_path}")

    out = {"model_kind": "soft_voting_rf_blend", "fixation_weight": float(args.fix_weight),
           "feature_columns": FEATURE_COLS, "label_meta": meta,
           "loso": {"cohen_kappa": k, "macro_f1": f, "balanced_accuracy": b},
           "live_responsiveness": resp, "n_windows": int(len(X)),
           "n_participants": int(pd.Series(g).nunique())}
    metrics_path = args.models_dir / f"rf_fixation{pct}_cv_metrics.json"
    metrics_path.write_text(json.dumps(out, indent=2))
    print(f"  Saved metrics -> {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
