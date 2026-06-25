"""Artifact directory helpers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACTS_ROOT = PROJECT_ROOT / "artifacts"
DEFAULT_CALLS_ROOT = DEFAULT_ARTIFACTS_ROOT / "calls"
SCENARIO_TYPE_BY_PREFIX = {
    "t": "smoke",
    "a": "appointment_scheduling",
    "m": "medication_refill",
    "i": "information_gathering",
    "e": "orthopedic_edge_cases",
    "d": "difficult_call_handling",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def scenario_type_for_id(scenario_id: str) -> str:
    normalized = scenario_id.strip().casefold()
    match = re.search(r"[a-z]", normalized)
    if match is None:
        return "unknown"
    return SCENARIO_TYPE_BY_PREFIX.get(match.group(0), "unknown")


def next_call_dir(root: Path = DEFAULT_CALLS_ROOT, call_type: str | None = None) -> Path:
    if call_type:
        root = root / call_type
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


def append_call_boundary_event(
    path: Path,
    boundary: str,
    *,
    call_id: str,
    scenario_id: str,
    call_type: str,
    details: dict[str, Any] | None = None,
) -> None:
    append_jsonl(
        path,
        {
            "time": utc_now_iso(),
            "event": "call.boundary",
            "boundary": boundary,
            "call_id": call_id,
            "scenario_id": scenario_id,
            "call_type": call_type,
            "details": details or {},
        },
    )
