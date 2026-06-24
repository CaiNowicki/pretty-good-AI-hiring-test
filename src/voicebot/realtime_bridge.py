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
DEFAULT_PREFIX_PADDING_MS = 500
DEFAULT_SILENCE_DURATION_MS = 1200
INTERRUPTION_PREFIX_PADDING_MS = 300
INTERRUPTION_SILENCE_DURATION_MS = 650
AGENT_SERVICE_OPENING_PHRASES = (
    "how may i help",
    "how can i help",
    "what can i help",
    "can i help",
    "how may i assist",
    "how can i assist",
    "how may we assist",
    "how can we assist",
    "what can we do",
    "what do you need",
    "what would you like",
    "what brings you in",
    "what are you calling about",
    "how may i direct your call",
)
INTAKE_BEFORE_GOAL_PHRASES = (
    "would you like to create",
    "patient profile",
    "demo patient profile",
    "what is your first name",
    "what's your first name",
    "what is your last name",
    "what's your last name",
    "date of birth",
    "birthdate",
    "dob",
    "phone number",
)
NON_CONVERSATIONAL_PHRASES = (
    "this call may be recorded",
    "thank you for calling",
    "thanks for calling",
    "para espanol",
    "para espa",
    "press",
    "oprima",
)


@dataclass
class BridgeState:
    stream_sid: str
    scenario: Scenario
    events_path: Path


def build_openai_realtime_url(settings: Settings) -> str:
    return f"{OPENAI_REALTIME_URL}?model={settings.realtime_model}"


def build_session_update(settings: Settings, scenario: Scenario) -> dict[str, Any]:
    bootstrap = build_realtime_bootstrap(scenario)
    prefix_padding_ms = (
        INTERRUPTION_PREFIX_PADDING_MS if scenario.interruption_test else DEFAULT_PREFIX_PADDING_MS
    )
    silence_duration_ms = (
        INTERRUPTION_SILENCE_DURATION_MS
        if scenario.interruption_test
        else DEFAULT_SILENCE_DURATION_MS
    )
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
                        "create_response": False,
                        "interrupt_response": True,
                        "prefix_padding_ms": prefix_padding_ms,
                        "silence_duration_ms": silence_duration_ms,
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
                "Only speak if the agent has clearly finished. Say this opening line exactly "
                "once, naturally, then wait for the agent: "
                f"{scenario.opening_line}"
            ),
        },
    }


def build_turn_response() -> dict[str, Any]:
    return {
        "type": "response.create",
        "response": {
            "instructions": (
                "Only speak if the agent has clearly finished. Respond as the patient for "
                "the current call turn. Keep it short, answer only what was asked, and wait "
                "for the agent after speaking."
            ),
        },
    }


def build_pre_goal_response() -> dict[str, Any]:
    return {
        "type": "response.create",
        "response": {
            "instructions": (
                "Only speak if the agent has clearly finished. "
                "Answer the agent's intake or profile setup question directly as the patient. "
                "Do not ask to schedule yet, do not repeat the opening line, and keep it brief."
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


def build_twilio_clear(stream_sid: str) -> dict[str, Any]:
    return {
        "event": "clear",
        "streamSid": stream_sid,
    }


def build_response_cancel() -> dict[str, str]:
    return {"type": "response.cancel"}


def transcript_is_service_opening(transcript: str) -> bool:
    normalized = transcript.casefold()
    return any(phrase in normalized for phrase in AGENT_SERVICE_OPENING_PHRASES)


def transcript_is_intake_before_goal(transcript: str) -> bool:
    normalized = transcript.casefold()
    return any(phrase in normalized for phrase in INTAKE_BEFORE_GOAL_PHRASES)


def transcript_is_ignorable_before_opening(transcript: str) -> bool:
    normalized = transcript.casefold()
    return any(phrase in normalized for phrase in NON_CONVERSATIONAL_PHRASES)


class RealtimeBridge:
    def __init__(self, settings: Settings, state: BridgeState):
        self.settings = settings
        self.state = state
        self._openai_ws: Any | None = None
        self._openai_to_twilio_task: asyncio.Task[None] | None = None
        self._goal_introduced = False
        self._bot_audio_in_progress = False

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
                self._bot_audio_in_progress = True
                await twilio_ws.send_json(build_twilio_media(self.state.stream_sid, event["delta"]))
                continue

            if event_type == "response.output_audio.done":
                self._bot_audio_in_progress = False
                await twilio_ws.send_json(
                    build_twilio_mark(
                        self.state.stream_sid,
                        f"audio-{event.get('response_id', 'done')}",
                    )
                )

            if event_type == "conversation.item.input_audio_transcription.completed":
                await self._maybe_create_patient_response(event)

            if event_type == "input_audio_buffer.speech_started":
                await self._handle_agent_speech_started(twilio_ws)

            if event_type in {
                "error",
                "session.created",
                "session.updated",
                "response.done",
                "response.output_audio_transcript.done",
                "response.output_audio_transcript.delta",
                "conversation.item.input_audio_transcription.completed",
                "input_audio_buffer.speech_started",
                "input_audio_buffer.speech_stopped",
                "input_audio_buffer.timeout_triggered",
            }:
                self._log({"event": "openai", "payload": event})

    def _log(self, payload: dict[str, Any]) -> None:
        append_jsonl(self.state.events_path, {"time": utc_now_iso(), **payload})

    async def _handle_agent_speech_started(self, twilio_ws: WebSocket) -> None:
        if not self._bot_audio_in_progress:
            return

        if self.state.scenario.interruption_test:
            self._log({"event": "agent_speech_during_bot_audio", "action": "allowed_for_test"})
            return

        self._bot_audio_in_progress = False
        self._log({"event": "agent_speech_during_bot_audio", "action": "yielded"})
        await self._send_openai(build_response_cancel())
        await twilio_ws.send_json(build_twilio_clear(self.state.stream_sid))

    async def _maybe_create_patient_response(self, event: dict[str, Any]) -> None:
        transcript = str(event.get("transcript", "")).strip()
        if not transcript:
            self._log({"event": "patient_response.skipped", "reason": "empty_transcript"})
            return

        if not self._goal_introduced:
            if transcript_is_service_opening(transcript):
                self._goal_introduced = True
                self._log({"event": "patient_response.goal_opening", "trigger": transcript})
                await self._send_openai(build_opening_response(self.state.scenario))
                return

            if transcript_is_ignorable_before_opening(transcript):
                self._log({"event": "patient_response.skipped", "reason": "pre_opening_ivr"})
                return

            if transcript_is_intake_before_goal(transcript):
                self._log({"event": "patient_response.pre_goal", "trigger": transcript})
                await self._send_openai(build_pre_goal_response())
                return

            self._log({"event": "patient_response.pre_goal", "trigger": transcript})
            await self._send_openai(build_pre_goal_response())
            return

        self._log({"event": "patient_response.turn", "trigger": transcript})
        await self._send_openai(build_turn_response())
