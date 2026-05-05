"""Lightweight parser for RTAPS/src/data/procedures.js.

We only need (procedure_id, step_id, step_number, time_threshold_s) for every
step in train1Procedures (train2 is a deepClone with cosmetic title changes
only). A regex-based extractor is sufficient and avoids needing a JS runtime.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import PROCEDURE_ID_TO_SLUG

_TRAIN1_OPEN_RE = re.compile(r"const\s+train1Procedures\s*=\s*\[")
# Allow JS-style line comments (`// ...`) between the `id:` and `name:` fields.
_PROC_HEADER_RE = re.compile(
    r"\{\s*id:\s*(?P<id>\d+)\s*,"
    r"(?:\s*//[^\n]*\n)*"
    r"\s*name:\s*\"(?P<name>[^\"]+)\"",
    re.DOTALL,
)


def _balanced_slice(text: str, open_idx: int, open_ch: str, close_ch: str) -> int:
    """Return the index of the matching close char, given the index of the open char."""
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
    raise ValueError(f"Unbalanced {open_ch}{close_ch} starting at {open_idx}")


@dataclass
class StepRow:
    procedure_id: int
    procedure_name: str
    procedure_slug: str
    step_id: int
    step_number: int
    time_threshold_s: float


def _split_top_level_steps(steps_body: str) -> list[str]:
    """Walk the `steps: [ ... ]` body and split on top-level `}, {` boundaries."""
    out: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(steps_body):
        if ch in "{[":
            depth += 1
            if depth == 1:
                start = i + 1
        elif ch in "}]":
            if depth == 1:
                out.append(steps_body[start:i])
            depth -= 1
    return [s.strip() for s in out if s.strip()]


def parse_procedures_js(path: Path) -> pd.DataFrame:
    """Return a DataFrame of one row per (procedure_id, step_id)."""
    text = path.read_text(encoding="utf-8")
    open_match = _TRAIN1_OPEN_RE.search(text)
    if not open_match:
        raise ValueError(f"Could not find train1Procedures in {path}")
    bracket_open = text.index("[", open_match.start())
    bracket_close = _balanced_slice(text, bracket_open, "[", "]")
    body = text[bracket_open + 1 : bracket_close]

    rows: list[StepRow] = []
    for proc_match in _PROC_HEADER_RE.finditer(body):
        pid = int(proc_match.group("id"))
        pname = proc_match.group("name")
        slug = PROCEDURE_ID_TO_SLUG.get(pid)
        if slug is None:
            continue
        steps_marker = body.find("steps:", proc_match.end())
        if steps_marker == -1:
            continue
        bracket = body.find("[", steps_marker)
        if bracket == -1:
            continue
        depth = 0
        end = None
        for i in range(bracket, len(body)):
            ch = body[i]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end is None:
            continue
        steps_body = body[bracket + 1 : end]
        for step_block in _split_top_level_steps(steps_body):
            sid_m = re.search(r"\bid:\s*(\d+)", step_block)
            sn_m = re.search(r"\bstepNumber:\s*(\d+)", step_block)
            tt_m = re.search(r"\btimeThreshold:\s*(\d+)", step_block)
            if sid_m and sn_m:
                rows.append(
                    StepRow(
                        procedure_id=pid,
                        procedure_name=pname,
                        procedure_slug=slug,
                        step_id=int(sid_m.group(1)),
                        step_number=int(sn_m.group(1)),
                        time_threshold_s=float(tt_m.group(1)) if tt_m else float("nan"),
                    )
                )
    if not rows:
        raise ValueError(f"Parsed zero steps from {path}")
    df = pd.DataFrame([r.__dict__ for r in rows])
    df = df.sort_values(["procedure_id", "step_number"]).reset_index(drop=True)
    return df
