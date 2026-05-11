"""Local model wrapper.

The trained classifier is `ML Algorithm/models/v2_hgb_vacp.joblib`. It was
saved as a dict (see `07_train_vacp_model.py`) with explicit
`feature_columns`, `categorical_columns`, and `label_order` so that the
serving code can validate the contract at load time and refuse to start if
the model and the live extractor have diverged.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.feature_extractor import FEATURE_NAMES

log = logging.getLogger(__name__)


class LocalPredictor:
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self._loaded: dict[str, Any] = {}
        self._model = None
        self._feature_cols: list[str] = []
        self._categorical_cols: list[str] = []
        self._label_order: list[str] = []

    def load(self) -> None:
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"Model file not found at {self.model_path}. "
                "Run `python 'ML Algorithm/scripts/07_train_vacp_model.py'` first, "
                "or set MODEL_PATH to a different location."
            )
        loaded = joblib.load(self.model_path)
        if not isinstance(loaded, dict) or "model" not in loaded:
            raise ValueError(
                f"Unexpected model artifact at {self.model_path}: "
                "expected a dict produced by 06_train_classifier.py"
            )
        self._loaded = loaded
        self._model = loaded["model"]
        self._feature_cols = list(loaded["feature_columns"])
        self._categorical_cols = list(loaded.get("categorical_columns", []))
        self._label_order = list(loaded["label_order"])

        if list(self._feature_cols) != list(FEATURE_NAMES):
            raise ValueError(
                "Feature contract mismatch — the model was trained on different\n"
                "columns than the live extractor produces.\n"
                f"  model.feature_columns: {self._feature_cols}\n"
                f"  live FEATURE_NAMES:    {list(FEATURE_NAMES)}\n"
                "Either retrain the model with the current FEATURE_NAMES or update\n"
                "feature_extractor.FEATURE_NAMES to match."
            )

        log.info(
            "Loaded model %s (%d features, classes=%s)",
            self.model_path, len(self._feature_cols), self._label_order,
        )

    @property
    def label_order(self) -> list[str]:
        return list(self._label_order)

    def predict(self, features: dict[str, float | int | None]) -> tuple[str, dict[str, float]]:
        """Return (predicted_label, per-class probabilities)."""
        if self._model is None:
            raise RuntimeError("Predictor not loaded. Call load() first.")
        row = {c: features.get(c, np.nan) for c in self._feature_cols}
        # Categorical columns must be re-typed to pandas category, same as training.
        df = pd.DataFrame([row], columns=self._feature_cols)
        for c in self._categorical_cols:
            df[c] = pd.Series(df[c].values, dtype="Int64").astype("category")
        proba = self._model.predict_proba(df)[0]
        classes = list(self._model.classes_)
        proba_map = {str(cls): float(p) for cls, p in zip(classes, proba)}
        # Order the dict by self._label_order so downstream consumers don't
        # have to think about it.
        ordered = {c: float(proba_map.get(c, 0.0)) for c in self._label_order}
        pred = max(ordered, key=ordered.get)
        return pred, ordered
