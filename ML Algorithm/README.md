# RTAPS ML

Builds the per-window training dataset for the RTAPS (Real-Time Adaptive
Procedure System) workload classifier. Eye-tracking and procedure-execution
logs from three laptops × three procedures (Centrifuge, Column Flushing,
Pressure Testing) are turned into a causal 10-second sliding-window feature
table suitable for training a workload (low / medium / high) model.

## Layout

```
ML Algorithm/
├── scripts/                # pipeline (5 stages) — see scripts/README.md
│   ├── 01_build_session_index.py
│   ├── 02_clean_pupil_export.py
│   ├── 03_align_steps.py
│   ├── 04_extract_features_window.py
│   ├── 05_summarize_per_step.py
│   ├── lib/                # shared modules (config, sync, io, features)
│   ├── requirements.txt
│   └── README.md
└── data/
    ├── Dr_Zahabi_laptop/   # raw Pupil exports + streaming captures (gitignored)
    ├── Lenovo_laptop/      # gitignored
    ├── Loaner_laptop/      # gitignored
    └── _processed/         # derived; small QA artifacts are committed
        ├── session_index.csv
        ├── procedure_steps.csv
        ├── baselines.csv
        ├── data_quality.csv
        ├── step_alignment_summary.csv
        ├── X_window_summary.csv
        ├── feature_dictionary.md
        └── {centrifuge,column_flushing,pressure_testing}/
            ├── X_window_sample.csv  (5 % stratified eyeball sample)
            └── per_session/...      (parquets — gitignored)
```

## Quick start

```bash
cd "ML Algorithm"
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/requirements.txt

# Place raw data into data/{Dr_Zahabi_laptop,Lenovo_laptop,Loaner_laptop}
# (laid out as Pupil Capture exports). Then:

python scripts/01_build_session_index.py
python scripts/02_clean_pupil_export.py
python scripts/03_align_steps.py
python scripts/04_extract_features_window.py     # add --labels_csv when labels are ready
python scripts/05_summarize_per_step.py
```

Full pipeline notes, design choices, and configuration knobs are in
[`scripts/README.md`](scripts/README.md).

## Output

The primary training table is `data/_processed/<procedure>/X_window.parquet`
(one row per causal 10 s / 1 s-stride window). The shipped artifacts in
`data/_processed/` (CSV + Markdown) document the schema and QA so a reviewer
can see what came out without having to rerun the pipeline.
