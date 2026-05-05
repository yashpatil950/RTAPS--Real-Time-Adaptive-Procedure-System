"""Per-window gaze / spatial-attention features.

Uses gaze_clean.parquet when available (richer x/y stats and transitions).
Falls back to fixation centroids for region entropy and top-1 ratio if gaze
isn't present.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

GAZE_FEATURE_NAMES = [
    "gaze_n_samples",
    "gaze_norm_x_mean",
    "gaze_norm_y_mean",
    "gaze_norm_x_std",
    "gaze_norm_y_std",
    "gaze_region_entropy",
    "gaze_region_top1_ratio",
    "gaze_transitions_per_sec",
]


def _region_id(x: np.ndarray, y: np.ndarray, grid_x: int, grid_y: int) -> np.ndarray:
    """Map (norm_pos_x, norm_pos_y) ∈ [0, 1]² to integer cell ids 0..(grid_x*grid_y - 1)."""
    cx = np.clip(np.floor(x * grid_x).astype(int), 0, grid_x - 1)
    cy = np.clip(np.floor(y * grid_y).astype(int), 0, grid_y - 1)
    return cy * grid_x + cx


def _entropy_top1(cells: np.ndarray, n_cells: int) -> tuple[float, float]:
    if len(cells) == 0:
        return float("nan"), float("nan")
    counts = np.bincount(cells, minlength=n_cells).astype(float)
    p = counts / counts.sum()
    nz = p[p > 0]
    h = float(-(nz * np.log2(nz)).sum())
    return h, float(p.max())


def extract(
    gaze_window: pd.DataFrame | None,
    fix_window: pd.DataFrame | None,
    *,
    window_len_s: float,
    grid: tuple[int, int],
) -> dict[str, float]:
    out: dict[str, float] = {k: float("nan") for k in GAZE_FEATURE_NAMES}
    out["gaze_n_samples"] = 0.0
    out["gaze_transitions_per_sec"] = 0.0

    grid_x, grid_y = grid
    n_cells = grid_x * grid_y

    if gaze_window is not None and len(gaze_window):
        x = gaze_window["norm_pos_x"].to_numpy(dtype=float)
        y = gaze_window["norm_pos_y"].to_numpy(dtype=float)
        out["gaze_n_samples"] = float(len(x))
        out["gaze_norm_x_mean"] = float(np.nanmean(x))
        out["gaze_norm_y_mean"] = float(np.nanmean(y))
        out["gaze_norm_x_std"] = float(np.nanstd(x, ddof=0))
        out["gaze_norm_y_std"] = float(np.nanstd(y, ddof=0))
        cells = _region_id(x, y, grid_x, grid_y)
        h, top1 = _entropy_top1(cells, n_cells)
        out["gaze_region_entropy"] = h
        out["gaze_region_top1_ratio"] = top1
        if len(cells) >= 2:
            transitions = int((np.diff(cells) != 0).sum())
            out["gaze_transitions_per_sec"] = float(transitions) / window_len_s
    elif fix_window is not None and len(fix_window) and {"norm_pos_x", "norm_pos_y"}.issubset(
        fix_window.columns
    ):
        # Fallback: fixation centroids
        x = fix_window["norm_pos_x"].to_numpy(dtype=float)
        y = fix_window["norm_pos_y"].to_numpy(dtype=float)
        out["gaze_norm_x_mean"] = float(np.nanmean(x))
        out["gaze_norm_y_mean"] = float(np.nanmean(y))
        if len(x) >= 2:
            out["gaze_norm_x_std"] = float(np.nanstd(x, ddof=0))
            out["gaze_norm_y_std"] = float(np.nanstd(y, ddof=0))
        cells = _region_id(x, y, grid_x, grid_y)
        h, top1 = _entropy_top1(cells, n_cells)
        out["gaze_region_entropy"] = h
        out["gaze_region_top1_ratio"] = top1
        if len(cells) >= 2:
            transitions = int((np.diff(cells) != 0).sum())
            out["gaze_transitions_per_sec"] = float(transitions) / window_len_s
    return out
