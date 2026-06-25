"""Prepare grouped scenario-call artifacts without originating calls."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from voicebot.artifacts import (
    DEFAULT_CALLS_ROOT,
    append_call_boundary_event,
    next_call_dir,
    scenario_type_for_id,
    utc_now_iso,
    write_json,
)
from voicebot.config import Settings
from voicebot.constants import ALLOWED_DESTINATION
from voicebot.scenario import load_scenario, ordered_scenario_stems, scenario_path_for_id
from voicebot.twilio_adapter import build_call_plan


@dataclass(frozen=True)
class PreparedScenarioCall:
    call_id: str
    call_type: str
    call_dir: Path
    scenario_id: str
    scenario_stem: str
    metadata_path: Path
    events_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "call_type": self.call_type,
            "call_dir": str(self.call_dir),
            "scenario_id": self.scenario_id,
            "scenario_stem": self.scenario_stem,
            "metadata_path": str(self.metadata_path),
            "events_path": str(self.events_path),
        }


def _call_id_for(call_type: str, call_dir: Path) -> str:
    return f"{call_type}-{call_dir.name}"


def prepare_scenario_call(
    settings: Settings,
    scenario_id: str,
    *,
    to_number: str = ALLOWED_DESTINATION,
    calls_root: Path = DEFAULT_CALLS_ROOT,
) -> PreparedScenarioCall:
    """Create a grouped call directory and dry-run call plan for one scenario."""

    scenario = load_scenario(scenario_id)
    scenario_path = scenario_path_for_id(scenario_id)
    scenario_stem = scenario_path.stem
    call_type = scenario_type_for_id(scenario_stem)
    call_dir = next_call_dir(calls_root, call_type)
    call_id = _call_id_for(call_type, call_dir)
    metadata_path = call_dir / "metadata.json"
    events_path = call_dir / "events.jsonl"
    created_at = utc_now_iso()
    call_plan = build_call_plan(settings, to_number, scenario_stem)

    shutil.copyfile(scenario_path, call_dir / "scenario.yaml")
    write_json(
        metadata_path,
        {
            "created_at": created_at,
            "call_id": call_id,
            "call_type": call_type,
            "scenario_id": scenario.id,
            "scenario_stem": scenario_stem,
            "status": "planned",
            "review_state": "not_started",
            "call_execution": {
                "enabled": False,
                "twilio_call_created": False,
                "twilio_call_sid": None,
            },
            "call_plan": call_plan,
            "limits": scenario.limits.to_dict(),
            "artifact_requirements": {
                "events_jsonl": "created",
                "scenario_yaml": "created",
                "metadata_json": "created",
                "recording_mp3_or_ogg": "pending_call_completion",
                "transcript_txt": "pending_call_completion",
                "analysis_md": "pending_manual_review",
            },
        },
    )
    append_call_boundary_event(
        events_path,
        "prepared",
        call_id=call_id,
        scenario_id=scenario.id,
        call_type=call_type,
        details={
            "status": "planned",
            "calls_enabled": False,
            "scenario_stem": scenario_stem,
        },
    )
    return PreparedScenarioCall(
        call_id=call_id,
        call_type=call_type,
        call_dir=call_dir,
        scenario_id=scenario.id,
        scenario_stem=scenario_stem,
        metadata_path=metadata_path,
        events_path=events_path,
    )


def prepare_scenario_call_batch(
    settings: Settings,
    scenario_ids: Iterable[str] | None = None,
    *,
    to_number: str = ALLOWED_DESTINATION,
    calls_root: Path = DEFAULT_CALLS_ROOT,
    limit: int | None = None,
) -> list[PreparedScenarioCall]:
    """Prepare grouped call artifacts for a scenario list without placing calls."""

    selected = list(scenario_ids if scenario_ids is not None else ordered_scenario_stems())
    if limit is not None:
        selected = selected[:limit]
    return [
        prepare_scenario_call(
            settings,
            scenario_id,
            to_number=to_number,
            calls_root=calls_root,
        )
        for scenario_id in selected
    ]
