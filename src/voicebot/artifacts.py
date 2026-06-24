"""Artifact directory helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def next_call_dir(root: Path = Path("artifacts/calls")) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    existing = sorted(path.name for path in root.glob("call-*") if path.is_dir())
    next_number = 1
    if existing:
        last = existing[-1].split("-")[-1]
        if last.isdigit():
            next_number = int(last) + 1
    call_dir = root / f"call-{next_number:03d}"
    call_dir.mkdir(parents=False, exist_ok=False)
    return call_dir


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
