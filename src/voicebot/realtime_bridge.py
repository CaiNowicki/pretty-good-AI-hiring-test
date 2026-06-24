"""Bridge Twilio Media Streams to the OpenAI Realtime API."""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websockets
from starlette.websockets import WebSocket

from voicebot.artifacts import append_jsonl, utc_now_iso
from voicebot.config import Settings
from voicebot.scenario import Scenario, build_realtime_bootstrap


OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
PCMU_FORMAT = {"type": "audio/pcmu"}


@dataclass
class BridgeState:
    stream_sid: str
    scenario: Scenario
    events_path: Path


def build_openai_realtime_url(settings: Settings) -> str:
    return f"{OPENAI_REALTIME_URL}?model={settings.realtime_model}"


def build_session_update(settings: Settings, scenario: Scenario) -> dict[str, Any]:
    bootstrap = build_realtime_bootstrap(scenario)
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": settings.realtime_model,
            "instructions": bootstrap["system_prompt"],
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": PCMU_FORMAT,
                    "transcription": {"model": settings.transcription_model},
                    "turn_detection": {
                        "type": "server_vad",
                        "create_response": True,
                        "interrupt_response": True,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 650,
                        "idle_timeout_ms": 10000,
                    },
                },
                "output": {
                    "format": PCMU_FORMAT,
                    "voice": "marin",
                },
            },
            "max_output_tokens": 1200,
        },
    }


def build_opening_response(scenario: Scenario) -> dict[str, Any]:
    return {
        "type": "response.create",
        "response": {
            "instructions": (
                "Say this opening line naturally, then wait for the agent: "
                f"{scenario.opening_line}"
            ),
        },
    }


def build_input_audio_append(payload: str) -> dict[str, str]:
    return {"type": "input_audio_buffer.append", "audio": payload}


def build_twilio_media(stream_sid: str, payload: str) -> dict[str, Any]:
    return {
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": payload},
    }


def build_twilio_mark(stream_sid: str, name: str) -> dict[str, Any]:
    return {
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {"name": name},
    }


class RealtimeBridge:
    def __init__(self, settings: Settings, state: BridgeState):
        self.settings = settings
        self.state = state
        self._openai_ws: Any | None = None
        self._openai_to_twilio_task: asyncio.Task[None] | None = None

    async def start(self, twilio_ws: WebSocket) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for the realtime bridge.")

        self._openai_ws = await websockets.connect(
            build_openai_realtime_url(self.settings),
            additional_headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "OpenAI-Safety-Identifier": "pretty-good-ai-hiring-test",
            },
        )
        await self._send_openai(build_session_update(self.settings, self.state.scenario))
        await self._send_openai(build_opening_response(self.state.scenario))
        self._openai_to_twilio_task = asyncio.create_task(self._pipe_openai_to_twilio(twilio_ws))
        self._log(
            {
                "event": "realtime.started",
                "scenario_id": self.state.scenario.id,
                "stream_sid": self.state.stream_sid,
            }
        )

    async def forward_twilio_media(self, payload: str) -> None:
        if self._openai_ws is None or not payload:
            return
        await self._send_openai(build_input_audio_append(payload))

    async def close(self) -> None:
        if self._openai_to_twilio_task is not None:
            self._openai_to_twilio_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._openai_to_twilio_task
        if self._openai_ws is not None:
            await self._openai_ws.close()
            self._openai_ws = None
        self._log({"event": "realtime.closed", "stream_sid": self.state.stream_sid})

    async def _send_openai(self, event: dict[str, Any]) -> None:
        if self._openai_ws is None:
            raise RuntimeError("Realtime WebSocket is not connected.")
        await self._openai_ws.send(json.dumps(event))

    async def _pipe_openai_to_twilio(self, twilio_ws: WebSocket) -> None:
        assert self._openai_ws is not None
        async for raw_message in self._openai_ws:
            event = json.loads(raw_message)
            event_type = event.get("type", "unknown")

            if event_type == "response.output_audio.delta":
                await twilio_ws.send_json(build_twilio_media(self.state.stream_sid, event["delta"]))
                continue

            if event_type == "response.output_audio.done":
                await twilio_ws.send_json(
                    build_twilio_mark(
                        self.state.stream_sid,
                        f"audio-{event.get('response_id', 'done')}",
                    )
                )

            if event_type in {
                "error",
                "session.created",
                "session.updated",
                "response.done",
                "response.output_audio_transcript.delta",
                "conversation.item.input_audio_transcription.completed",
                "input_audio_buffer.speech_started",
                "input_audio_buffer.speech_stopped",
                "input_audio_buffer.timeout_triggered",
            }:
                self._log({"event": "openai", "payload": event})

    def _log(self, payload: dict[str, Any]) -> None:
        append_jsonl(self.state.events_path, {"time": utc_now_iso(), **payload})
