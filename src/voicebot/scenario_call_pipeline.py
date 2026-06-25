"""Prepare grouped scenario-call artifacts without originating calls."""

from __future__ import annotations

import json
import shutil
import time
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
from voicebot.twilio_adapter import build_call_plan, create_outbound_call


DEFAULT_COMPLETION_TIMEOUT_SECONDS = 900.0
DEFAULT_COMPLETION_POLL_SECONDS = 2.0


@dataclass(frozen=True)
class PreparedScenarioCall:
    call_id: str
    call_type: str
    call_dir: Path
    scenario_id: str
    scenario_stem: str
    metadata_path: Path
    events_path: Path
    transcript_path: Path
    recording_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "call_type": self.call_type,
            "call_dir": str(self.call_dir),
            "scenario_id": self.scenario_id,
            "scenario_stem": self.scenario_stem,
            "metadata_path": str(self.metadata_path),
            "events_path": str(self.events_path),
            "transcript_path": str(self.transcript_path),
            "recording_path": str(self.recording_path),
        }


def _call_id_for(call_type: str, call_dir: Path) -> str:
    return f"{call_type}-{call_dir.name}"


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    write_json(path, metadata)


def _set_artifact_status(call_dir: Path, artifact_name: str, status: str) -> None:
    metadata_path = call_dir / "metadata.json"
    metadata = _read_metadata(metadata_path)
    artifact_requirements = dict(metadata.get("artifact_requirements", {}))
    artifact_requirements[artifact_name] = status
    metadata["artifact_requirements"] = artifact_requirements
    _write_metadata(metadata_path, metadata)


def update_call_metadata(call_dir: Path, updates: dict[str, Any]) -> None:
    metadata_path = call_dir / "metadata.json"
    metadata = _read_metadata(metadata_path)
    metadata.update(updates)
    _write_metadata(metadata_path, metadata)


def _openai_transcript_turn(payload: dict[str, Any]) -> tuple[str, str] | None:
    event_type = payload.get("type")
    if event_type == "conversation.item.input_audio_transcription.completed":
        speaker = "PGAI Agent"
    elif event_type == "response.output_audio_transcript.done":
        speaker = "Patient Bot"
    else:
        return None

    transcript = " ".join(str(payload.get("transcript", "")).split())
    if not transcript:
        return None
    return speaker, transcript


def write_transcript_from_events(
    events_path: Path,
    transcript_path: Path | None = None,
) -> Path:
    """Create a speaker-labeled transcript from realtime OpenAI transcript events."""

    if transcript_path is None:
        transcript_path = events_path.parent / "transcript.txt"

    turns: list[tuple[str, str]] = []
    if events_path.exists():
        for raw_line in events_path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if event.get("event") != "openai":
                continue
            turn = _openai_transcript_turn(event.get("payload", {}))
            if turn is None:
                continue
            if turns and turns[-1] == turn:
                continue
            turns.append(turn)

    transcript_path.parent.mkdir(parents=True, exist_ok=True)
    if turns:
        lines = [f"{speaker}: {text}" for speaker, text in turns]
        transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _set_artifact_status(transcript_path.parent, "transcript_txt", "created")
    else:
        transcript_path.write_text("", encoding="utf-8")
        _set_artifact_status(transcript_path.parent, "transcript_txt", "empty_no_turns_found")
    return transcript_path


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
    transcript_path = call_dir / "transcript.txt"
    recording_path = call_dir / "recording.mp3"
    created_at = utc_now_iso()
    call_plan = build_call_plan(
        settings,
        to_number,
        scenario_stem,
        call_id=call_id,
        call_type=call_type,
        call_dir_name=call_dir.name,
    )

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
        transcript_path=transcript_path,
        recording_path=recording_path,
    )


def start_prepared_scenario_call(
    settings: Settings,
    prepared: PreparedScenarioCall,
    *,
    to_number: str = ALLOWED_DESTINATION,
) -> dict[str, Any]:
    """Originate a Twilio call for an already-prepared artifact directory."""

    append_call_boundary_event(
        prepared.events_path,
        "start_requested",
        call_id=prepared.call_id,
        scenario_id=prepared.scenario_id,
        call_type=prepared.call_type,
        details={"calls_enabled": True, "scenario_stem": prepared.scenario_stem},
    )
    try:
        result = create_outbound_call(
            settings,
            to_number,
            prepared.scenario_stem,
            call_id=prepared.call_id,
            call_type=prepared.call_type,
            call_dir_name=prepared.call_dir.name,
        )
    except Exception as exc:
        update_call_metadata(
            prepared.call_dir,
            {
                "status": "call_start_failed",
                "call_execution": {
                    "enabled": True,
                    "twilio_call_created": False,
                    "twilio_call_sid": None,
                    "error": str(exc),
                },
            },
        )
        append_call_boundary_event(
            prepared.events_path,
            "start_failed",
            call_id=prepared.call_id,
            scenario_id=prepared.scenario_id,
            call_type=prepared.call_type,
            details={"error": str(exc)},
        )
        raise

    update_call_metadata(
        prepared.call_dir,
        {
            "status": "in_progress",
            "call_execution": {
                "enabled": True,
                "twilio_call_created": True,
                "twilio_call_sid": result["sid"],
                "twilio_call_status": result["status"],
            },
            "twilio_call": result,
            "artifact_requirements": {
                "events_jsonl": "created",
                "scenario_yaml": "created",
                "metadata_json": "created",
                "recording_mp3_or_ogg": "pending_recording_callback",
                "transcript_txt": "pending_media_stream_completion",
                "analysis_md": "pending_manual_review",
            },
        },
    )
    append_call_boundary_event(
        prepared.events_path,
        "started",
        call_id=prepared.call_id,
        scenario_id=prepared.scenario_id,
        call_type=prepared.call_type,
        details={"twilio_call_sid": result["sid"], "status": result["status"]},
    )
    return result


def _event_marks_call_completion(event: dict[str, Any]) -> bool:
    if event.get("event") == "twilio.recording_callback":
        return True
    return event.get("event") == "call.boundary" and event.get("boundary") == "end"


def wait_for_prepared_call_completion(
    prepared: PreparedScenarioCall,
    *,
    timeout_seconds: float = DEFAULT_COMPLETION_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_COMPLETION_POLL_SECONDS,
) -> None:
    """Block until the webhook server records that a live call has completed."""

    deadline = time.monotonic() + timeout_seconds
    while True:
        if prepared.events_path.exists():
            for raw_line in prepared.events_path.read_text(encoding="utf-8").splitlines():
                if not raw_line.strip():
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if _event_marks_call_completion(event):
                    return

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for live call completion: {prepared.call_id}"
            )
        time.sleep(poll_seconds)


def run_scenario_call(
    settings: Settings,
    scenario_id: str,
    *,
    live: bool,
    to_number: str = ALLOWED_DESTINATION,
    calls_root: Path = DEFAULT_CALLS_ROOT,
) -> PreparedScenarioCall:
    """Prepare one scenario and optionally originate the live Twilio call."""

    prepared = prepare_scenario_call(
        settings,
        scenario_id,
        to_number=to_number,
        calls_root=calls_root,
    )
    if live:
        start_prepared_scenario_call(settings, prepared, to_number=to_number)
    return prepared


def run_scenario_call_batch(
    settings: Settings,
    scenario_ids: Iterable[str] | None = None,
    *,
    live: bool,
    to_number: str = ALLOWED_DESTINATION,
    calls_root: Path = DEFAULT_CALLS_ROOT,
    limit: int | None = None,
    inter_call_delay_seconds: float = 0.0,
    wait_for_completion: bool = False,
    completion_timeout_seconds: float = DEFAULT_COMPLETION_TIMEOUT_SECONDS,
) -> list[PreparedScenarioCall]:
    """Prepare each selected scenario and optionally start Twilio calls in order."""

    selected = list(scenario_ids if scenario_ids is not None else ordered_scenario_stems())
    if limit is not None:
        selected = selected[:limit]

    prepared: list[PreparedScenarioCall] = []
    for index, scenario_id in enumerate(selected):
        prepared_call = run_scenario_call(
            settings,
            scenario_id,
            live=live,
            to_number=to_number,
            calls_root=calls_root,
        )
        prepared.append(prepared_call)
        if live and index < len(selected) - 1:
            if wait_for_completion:
                wait_for_prepared_call_completion(
                    prepared_call,
                    timeout_seconds=completion_timeout_seconds,
                )
            if inter_call_delay_seconds > 0:
                time.sleep(inter_call_delay_seconds)
    return prepared


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
