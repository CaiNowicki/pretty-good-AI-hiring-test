"""FastAPI app for Twilio webhooks and Media Streams."""

from __future__ import annotations

from html import escape
from pathlib import Path

from voicebot.artifacts import append_jsonl, utc_now_iso
from voicebot.config import load_settings
from voicebot.constants import DEFAULT_SCENARIO_ID
from voicebot.realtime_bridge import BridgeState, RealtimeBridge
from voicebot.scenario import ScenarioNotFoundError, load_scenario

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import Response
except ImportError as exc:  # pragma: no cover - import guard for dependency-free tests
    raise RuntimeError("Install project dependencies before importing the server.") from exc


app = FastAPI(title="Pretty Good AI Voice Bot")


def _scenario_id_from_start_event(message: dict) -> str:
    start = message.get("start", {})
    custom_parameters = start.get("customParameters", {})
    scenario_id = custom_parameters.get("scenario_id", DEFAULT_SCENARIO_ID)
    return scenario_id


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": utc_now_iso()}


@app.api_route("/twilio/voice", methods=["GET", "POST"])
def twilio_voice(scenario_id: str = DEFAULT_SCENARIO_ID) -> Response:
    settings = load_settings()
    stream_url = f"{settings.public_ws_base_url.rstrip('/')}/twilio/media"
    scenario = escape(scenario_id, quote=True)
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{stream_url}">
      <Parameter name="scenario_id" value="{scenario}" />
    </Stream>
  </Connect>
</Response>
"""
    return Response(content=twiml, media_type="application/xml")


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

            if event_type in {"connected", "mark", "dtmf"}:
                append_jsonl(events_path, {"time": utc_now_iso(), "twilio": message})
    except WebSocketDisconnect:
        append_jsonl(events_path, {"time": utc_now_iso(), "event": "websocket.disconnected"})
    finally:
        if bridge is not None:
            await bridge.close()
