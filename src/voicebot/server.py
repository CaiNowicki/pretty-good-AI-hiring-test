"""FastAPI app for Twilio webhooks and Media Streams."""

from __future__ import annotations

import base64
import re
from html import escape
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import Request as UrlRequest, urlopen

from voicebot.artifacts import append_jsonl, utc_now_iso
from voicebot.config import load_settings
from voicebot.constants import DEFAULT_SCENARIO_ID
from voicebot.realtime_bridge import EMERGENCY_STOP_DTMF_DIGITS, BridgeState, RealtimeBridge
from voicebot.scenario import ScenarioNotFoundError, load_scenario
from voicebot.scenario_call_pipeline import update_call_metadata, write_transcript_from_events

try:
    from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import Response
except ImportError as exc:  # pragma: no cover - import guard for dependency-free tests
    raise RuntimeError("Install project dependencies before importing the server.") from exc


app = FastAPI(title="Pretty Good AI Voice Bot")
SAFE_CALL_TYPE_RE = re.compile(r"^[a-z_]+$")
SAFE_CALL_DIR_RE = re.compile(r"^call-\d{3,}$")


def _scenario_id_from_start_event(message: dict) -> str:
    start = message.get("start", {})
    custom_parameters = start.get("customParameters", {})
    scenario_id = custom_parameters.get("scenario_id", DEFAULT_SCENARIO_ID)
    return scenario_id


def _custom_parameters_from_start_event(message: dict) -> dict[str, str]:
    start = message.get("start", {})
    custom_parameters = start.get("customParameters", {})
    if not isinstance(custom_parameters, dict):
        return {}
    return {str(key): str(value) for key, value in custom_parameters.items()}


def _call_events_path(
    *,
    call_type: str = "",
    call_dir_name: str = "",
) -> Path | None:
    if not call_type or not call_dir_name:
        return None
    if not SAFE_CALL_TYPE_RE.fullmatch(call_type):
        return None
    if not SAFE_CALL_DIR_RE.fullmatch(call_dir_name):
        return None
    return Path("artifacts") / "calls" / call_type / call_dir_name / "events.jsonl"


def _call_metadata_from_start_event(message: dict) -> dict[str, str]:
    params = _custom_parameters_from_start_event(message)
    return {
        "call_id": params.get("call_id", ""),
        "call_type": params.get("call_type", ""),
        "call_dir_name": params.get("call_dir_name", ""),
    }


def _write_transcript_if_possible(events_path: Path) -> None:
    transcript_path = write_transcript_from_events(events_path)
    append_jsonl(
        events_path,
        {
            "time": utc_now_iso(),
            "event": "artifact.transcript_written",
            "path": str(transcript_path),
        },
    )


def _download_recording(settings, recording_url: str, recording_path: Path) -> None:
    download_url = recording_url if recording_url.endswith(".mp3") else f"{recording_url}.mp3"
    token = f"{settings.twilio_account_sid}:{settings.twilio_auth_token}".encode("utf-8")
    request = UrlRequest(
        download_url,
        headers={"Authorization": f"Basic {base64.b64encode(token).decode('ascii')}"},
    )
    recording_path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(request, timeout=30) as response:
        recording_path.write_bytes(response.read())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": utc_now_iso()}


@app.api_route("/twilio/voice", methods=["GET", "POST"])
def twilio_voice(
    scenario_id: str = DEFAULT_SCENARIO_ID,
    call_id: str = "",
    call_type: str = "",
    call_dir_name: str = "",
) -> Response:
    settings = load_settings()
    stream_url = f"{settings.public_ws_base_url.rstrip('/')}/twilio/media"
    scenario = escape(scenario_id, quote=True)
    escaped_call_id = escape(call_id, quote=True)
    escaped_call_type = escape(call_type, quote=True)
    escaped_call_dir_name = escape(call_dir_name, quote=True)
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{stream_url}">
      <Parameter name="scenario_id" value="{scenario}" />
      <Parameter name="call_id" value="{escaped_call_id}" />
      <Parameter name="call_type" value="{escaped_call_type}" />
      <Parameter name="call_dir_name" value="{escaped_call_dir_name}" />
    </Stream>
  </Connect>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")


@app.api_route("/twilio/recording", methods=["GET", "POST"])
async def twilio_recording(
    request: Request,
    call_id: str = "",
    call_type: str = "",
    call_dir_name: str = "",
) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    form = {key: values[0] for key, values in parse_qs(body).items() if values}
    recording_url = form.get("RecordingUrl", "")
    recording_sid = form.get("RecordingSid", "")
    recording_status = form.get("RecordingStatus", "")
    events_path = _call_events_path(call_type=call_type, call_dir_name=call_dir_name)
    if events_path is None:
        events_path = Path("artifacts") / "recording-events.jsonl"

    append_jsonl(
        events_path,
        {
            "time": utc_now_iso(),
            "event": "twilio.recording_callback",
            "call_id": call_id,
            "recording_sid": recording_sid,
            "recording_status": recording_status,
            "recording_url_present": bool(recording_url),
        },
    )

    if recording_url and events_path.parent.name.startswith("call-"):
        settings = load_settings()
        recording_path = events_path.parent / "recording.mp3"
        try:
            _download_recording(settings, recording_url, recording_path)
        except (OSError, URLError, TimeoutError) as exc:
            append_jsonl(
                events_path,
                {
                    "time": utc_now_iso(),
                    "event": "artifact.recording_download_failed",
                    "error": str(exc),
                    "recording_sid": recording_sid,
                },
            )
            update_call_metadata(
                events_path.parent,
                {"status": "recording_download_failed", "recording_error": str(exc)},
            )
        else:
            append_jsonl(
                events_path,
                {
                    "time": utc_now_iso(),
                    "event": "artifact.recording_downloaded",
                    "path": str(recording_path),
                    "recording_sid": recording_sid,
                },
            )
            update_call_metadata(
                events_path.parent,
                {
                    "status": "recording_received",
                    "recording_path": str(recording_path),
                    "artifact_requirements": {
                        "events_jsonl": "created",
                        "scenario_yaml": "created",
                        "metadata_json": "created",
                        "recording_mp3_or_ogg": "created",
                        "transcript_txt": (
                            "created"
                            if (events_path.parent / "transcript.txt").exists()
                            else "pending_media_stream_completion"
                        ),
                        "analysis_md": "pending_manual_review",
                    },
                },
            )

    if events_path.exists() and events_path.parent.name.startswith("call-"):
        _write_transcript_if_possible(events_path)
    return {"status": "ok"}


@app.websocket("/twilio/media")
async def twilio_media(websocket: WebSocket) -> None:
    await websocket.accept()
    events_path = websocket.app.state.__dict__.get("events_path")
    if events_path is None:
        events_path = Path("artifacts/media-events.jsonl")

    append_jsonl(events_path, {"time": utc_now_iso(), "event": "websocket.accepted"})
    settings = load_settings()
    bridge: RealtimeBridge | None = None

    try:
        while True:
            message = await websocket.receive_json()
            event_type = message.get("event", "unknown")
            if event_type == "start":
                call_metadata = _call_metadata_from_start_event(message)
                call_events_path = _call_events_path(
                    call_type=call_metadata["call_type"],
                    call_dir_name=call_metadata["call_dir_name"],
                )
                if call_events_path is not None:
                    events_path = call_events_path
                append_jsonl(events_path, {"time": utc_now_iso(), "twilio": message})
                scenario_id = _scenario_id_from_start_event(message)
                try:
                    scenario = load_scenario(scenario_id)
                except ScenarioNotFoundError as exc:
                    append_jsonl(
                        events_path,
                        {
                            "time": utc_now_iso(),
                            "event": "scenario.load_failed",
                            "scenario_id": scenario_id,
                            "error": str(exc),
                        },
                    )
                    continue

                start = message.get("start", {})
                stream_sid = message.get("streamSid") or start.get("streamSid")
                if not stream_sid:
                    append_jsonl(
                        events_path,
                        {
                            "time": utc_now_iso(),
                            "event": "twilio.start_missing_stream_sid",
                            "scenario_id": scenario_id,
                        },
                    )
                    continue

                bridge = RealtimeBridge(
                    settings,
                    BridgeState(
                        stream_sid=stream_sid,
                        scenario=scenario,
                        events_path=events_path,
                        call_id=call_metadata["call_id"],
                        call_type=call_metadata["call_type"],
                    ),
                )
                await bridge.start(websocket)
                continue

            if event_type == "media":
                append_jsonl(
                    events_path,
                    {
                        "time": utc_now_iso(),
                        "event": "media",
                        "track": message.get("media", {}).get("track"),
                        "chunk": message.get("media", {}).get("chunk"),
                    },
                )
                if bridge is not None:
                    await bridge.forward_twilio_media(message.get("media", {}).get("payload", ""))
                continue

            if event_type == "stop":
                append_jsonl(events_path, {"time": utc_now_iso(), "twilio": message})
                if bridge is not None:
                    await bridge.close()
                    bridge = None
                break

            if event_type == "dtmf":
                append_jsonl(events_path, {"time": utc_now_iso(), "twilio": message})
                digit = str(message.get("dtmf", {}).get("digits", ""))
                if bridge is not None and digit in EMERGENCY_STOP_DTMF_DIGITS:
                    await bridge.request_emergency_stop(websocket, f"dtmf:{digit}")
                    bridge = None
                    break
                continue

            if event_type == "mark":
                append_jsonl(events_path, {"time": utc_now_iso(), "twilio": message})
                mark_name = str(message.get("mark", {}).get("name", ""))
                if bridge is not None and await bridge.handle_twilio_mark(websocket, mark_name):
                    bridge = None
                    break
                continue

            if event_type == "connected":
                append_jsonl(events_path, {"time": utc_now_iso(), "twilio": message})
    except WebSocketDisconnect:
        append_jsonl(events_path, {"time": utc_now_iso(), "event": "websocket.disconnected"})
    finally:
        if bridge is not None:
            await bridge.close()
        if events_path.exists() and events_path.parent.name.startswith("call-"):
            _write_transcript_if_possible(events_path)
