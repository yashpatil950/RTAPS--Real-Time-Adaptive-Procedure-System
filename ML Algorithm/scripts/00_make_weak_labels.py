#!/usr/bin/env python3
"""Stage 0: derive weak workload labels from `rtaps_sessions.csv`.

Output: `data/_processed/labels_weak.csv` with columns
    (session_uid, step_number, step_id, workload_label, source)

Rule (proxy — see X_FEATURES.md §9 / Y_LABELS issue):
    subStepsShown == True  AND exceededThreshold == True   -> "high"
    subStepsShown == False AND exceededThreshold == False  -> "low"
    otherwise                                              -> "medium"

Rationale: the RTAPS UI escalated guidance (`subStepsShown=true`) when an
operator was struggling; `exceededThreshold=true` means they ran past the step
time threshold defined in `procedures.js`. The combination is a reasonable
post-hoc workload proxy. It is **not** a real ground-truth label — replace as
soon as we have NASA-TLX / SOA / annotator data.

Run:
    python "ML Algorithm/scripts/00_make_weak_labels.py"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import PROCESSED_ROOT, RTAPS_SESSIONS_CSV  # noqa: E402
from lib.io_utils import load_rtaps_sessions  # noqa: E402

LABEL_SOURCE_TAG = "weak_rule_v1"


def _label_for(sub_steps_shown: bool, exceeded_threshold: bool) -> str:
    if sub_steps_shown and exceeded_threshold:
        return "high"
    if (not sub_steps_shown) and (not exceeded_threshold):
        return "low"
    return "medium"


def build_labels(sessions_csv: Path, processed_root: Path) -> pd.DataFrame:
    """Join `rtaps_sessions` (the label source) with `session_index` (the keys
    used by every other stage) so `session_uid` is the join key downstream.
    """
    sidx_path = processed_root / "session_index.csv"
    if not sidx_path.is_file():
        raise FileNotFoundError(
            f"{sidx_path} missing; run 01_build_session_index.py first."
        )
    sidx = pd.read_csv(sidx_path)
    sidx = sidx[sidx["rtaps_session_id"].notna()][["session_uid", "rtaps_session_id"]]

    rt = load_rtaps_sessions(sessions_csv)
    rt = rt[rt["sessionId"].isin(sidx["rtaps_session_id"])].copy()

    rows: list[dict] = []
    for _, sess in rt.iterrows():
        rtaps_id = sess["sessionId"]
        sess_uids = sidx.loc[sidx["rtaps_session_id"] == rtaps_id, "session_uid"].tolist()
        for sess_uid in sess_uids:
            for step in sess["parsed_steps"]:
                step_no = step.get("stepNumber")
                if step_no is None:
                    continue
                rows.append(
                    {
                        "session_uid": sess_uid,
                        "step_number": int(step_no),
                        "step_id": int(step.get("stepId")) if step.get("stepId") is not None else pd.NA,
                        "workload_label": _label_for(
                            bool(step.get("subStepsShown", False)),
                            bool(step.get("exceededThreshold", False)),
                        ),
                        "source": LABEL_SOURCE_TAG,
                    }
                )

    out = pd.DataFrame(rows).sort_values(["session_uid", "step_number"]).reset_index(drop=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed_root", type=Path, default=PROCESSED_ROOT)
    ap.add_argument("--sessions_csv", type=Path, default=RTAPS_SESSIONS_CSV)
    ap.add_argument("--out", type=Path, default=None,
                    help="Override output path (default: <processed_root>/labels_weak.csv)")
    args = ap.parse_args(argv)

    if not args.sessions_csv.is_file():
        print(f"ERROR: rtaps_sessions.csv not found at {args.sessions_csv}")
        return 2

    labels = build_labels(args.sessions_csv, args.processed_root)
    out_path = args.out or (args.processed_root / "labels_weak.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    labels.to_csv(out_path, index=False)

    counts = labels["workload_label"].value_counts().to_dict()
    print(f"wrote {out_path}: {len(labels)} (session_uid, step_number) rows")
    print(f"  class distribution: {counts}")
    print(f"  unique sessions:    {labels['session_uid'].nunique()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
