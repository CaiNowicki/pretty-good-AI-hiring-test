"""Bridge Twilio Media Streams to the OpenAI Realtime API."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
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
DEFAULT_SILENCE_DURATION_MS = 650
DEFAULT_RESPONSE_DELAY_SECONDS = 0.1
POST_VAD_SILENCE_CONFIRMATION_SECONDS = 0.15
POST_RESPONSE_COOLDOWN_SECONDS = 0.5
INTERRUPTION_PREFIX_PADDING_MS = 300
INTERRUPTION_SILENCE_DURATION_MS = 650
INTERRUPTION_RESPONSE_DELAY_SECONDS = 0.25
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
WAIT_FOR_AGENT_TO_CONTINUE_PHRASES = (
    "thanks for confirming",
    "specific provider you'd like to see or",
    "it looks",
    "for you",
)
CONFUSING_AGENT_PHRASES = (
    "dental purposes",
    "birthdate doesn't match",
    "date of birth doesn't match",
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


def build_turn_response(scenario: Scenario | None = None, transcript: str = "") -> dict[str, Any]:
    exact_answer = build_exact_fact_answer(scenario, transcript) if scenario is not None else ""
    if exact_answer:
        instructions = f"Say only this exact patient answer: {exact_answer}"
    else:
        instructions = (
            "Only speak if the agent has clearly finished. Respond as the patient for "
            "the current call turn. Keep it short, answer only what was asked, use the "
            "scenario facts exactly, do not add unrelated preferences or comments, and "
            "wait for the agent after speaking."
        )

    return {
        "type": "response.create",
        "response": {
            "instructions": instructions,
        },
    }


def build_pre_goal_response(scenario: Scenario | None = None, transcript: str = "") -> dict[str, Any]:
    exact_answer = build_exact_fact_answer(scenario, transcript) if scenario is not None else ""
    if exact_answer:
        instructions = f"Say only this exact patient answer: {exact_answer}"
    else:
        instructions = (
            "Only speak if the agent has clearly finished. "
            "Answer the agent's intake or profile setup question directly as the patient. "
            "Do not ask to schedule yet, do not repeat the opening line, use the scenario "
            "facts exactly, do not add unrelated preferences or comments, and keep it brief."
        )

    return {
        "type": "response.create",
        "response": {
            "instructions": instructions,
        },
    }


def build_confusion_response(scenario: Scenario, transcript: str) -> dict[str, Any]:
    return {
        "type": "response.create",
        "response": {
            "instructions": (
                "Say only this one short clarification sentence, then wait: "
                f"{build_confusion_reply(scenario, transcript)}"
            ),
        },
    }


def build_exact_fact_answer(scenario: Scenario | None, transcript: str) -> str:
    if scenario is None:
        return ""

    normalized = transcript.casefold()
    goal = scenario.goal.casefold()
    name = scenario.facts.get("name", "").strip()
    name_parts = name.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[-1] if len(name_parts) > 1 else ""

    if "date of birth" in normalized or "birthdate" in normalized or "dob" in normalized:
        dob = scenario.facts.get("date_of_birth", "").strip()
        return f"My date of birth is {dob}." if dob else ""
    if "first name" in normalized and first_name:
        return first_name
    if "last name" in normalized and last_name:
        return last_name
    if "your name" in normalized and name:
        return name
    if "phone" in normalized:
        phone = scenario.facts.get("phone", "").strip()
        return phone
    if _asks_about_appointment_type(normalized):
        if "new patient consultation" in goal:
            return "It's a new patient consultation, not a follow-up."
        if "routine visit" in goal:
            return "It's a routine visit."
        if "reschedule" in goal or "move an existing appointment" in goal:
            return "I'm calling to reschedule an existing appointment."
        if "cancel" in goal:
            return "I'm calling to cancel an appointment."
    return ""


def build_confusion_reply(scenario: Scenario, transcript: str) -> str:
    normalized = transcript.casefold()
    goal = scenario.goal.casefold()

    if "birthdate doesn't match" in normalized or "date of birth doesn't match" in normalized:
        dob = scenario.facts.get("date_of_birth", "").strip()
        return f"I don't understand. My date of birth is {dob}." if dob else "I don't understand."

    if "dental" in normalized:
        return "I don't understand; I thought I called orthopedics."

    if "new patient" in goal and (
        "already have" in normalized
        or "reschedule or cancel" in normalized
        or "reschedule your appointment" in normalized
    ):
        return "I don't understand; I'm trying to schedule a new patient consultation."

    return "I don't understand what you mean."


def _asks_about_appointment_type(normalized_transcript: str) -> bool:
    return any(
        phrase in normalized_transcript
        for phrase in (
            "appointment type",
            "type of appointment",
            "reason for visit",
            "new patient consultation",
            "follow-up",
            "followup",
            "routine visit",
        )
    )


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


def transcript_needs_more_agent_context(transcript: str) -> bool:
    normalized = transcript.casefold().strip()
    if not normalized:
        return True
    if transcript_is_service_opening(normalized) or transcript_is_intake_before_goal(normalized):
        return False
    if "?" in normalized:
        return False
    if any(phrase in normalized for phrase in WAIT_FOR_AGENT_TO_CONTINUE_PHRASES):
        return True
    if normalized.endswith((" or", " and", " to", " with")):
        return True
    return len(normalized.split()) <= 3


def transcript_is_confusing_or_out_of_turn(scenario: Scenario, transcript: str) -> bool:
    normalized = transcript.casefold().strip()
    if any(phrase in normalized for phrase in CONFUSING_AGENT_PHRASES):
        return True
    if "new patient" in scenario.goal.casefold() and (
        "already have" in normalized
        or "reschedule or cancel" in normalized
        or "reschedule your appointment" in normalized
    ):
        return True
    return _looks_like_garbled_transcript(transcript)


def build_agent_turn_key(event: dict[str, Any]) -> str:
    item_id = event.get("item_id")
    if not item_id and isinstance(event.get("item"), dict):
        item_id = event["item"].get("id")
    if item_id:
        return f"item:{item_id}"

    transcript = str(event.get("transcript", ""))
    normalized = re.sub(r"\s+", " ", transcript.casefold()).strip()
    return f"text:{normalized[:160]}"


def _looks_like_garbled_transcript(transcript: str) -> bool:
    text = transcript.strip()
    if not text:
        return False
    non_ascii = sum(1 for char in text if ord(char) > 127)
    return non_ascii >= 3 and non_ascii / max(len(text), 1) > 0.35


class RealtimeBridge:
    def __init__(self, settings: Settings, state: BridgeState):
        self.settings = settings
        self.state = state
        self._openai_ws: Any | None = None
        self._openai_to_twilio_task: asyncio.Task[None] | None = None
        self._pending_response_task: asyncio.Task[None] | None = None
        self._pending_transcript_event: dict[str, Any] | None = None
        self._agent_speech_in_progress = False
        self._last_agent_speech_stopped_at = 0.0
        self._goal_introduced = False
        self._bot_audio_in_progress = False
        self._patient_response_in_progress = False
        self._cooldown_until = 0.0
        self._responded_agent_turns: set[str] = set()

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
        if self._pending_response_task is not None:
            self._pending_response_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pending_response_task
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
                self._finish_patient_response_cooldown()
                await twilio_ws.send_json(
                    build_twilio_mark(
                        self.state.stream_sid,
                        f"audio-{event.get('response_id', 'done')}",
                    )
                )

            if event_type == "response.done" and self._patient_response_in_progress:
                self._finish_patient_response_cooldown()

            if event_type == "conversation.item.input_audio_transcription.completed":
                self._schedule_patient_response(event)

            if event_type == "input_audio_buffer.speech_started":
                await self._handle_agent_speech_started(twilio_ws)

            if event_type == "input_audio_buffer.speech_stopped":
                self._handle_agent_speech_stopped()

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

    def _schedule_patient_response(self, event: dict[str, Any]) -> None:
        self._pending_transcript_event = dict(event)
        if self._agent_speech_in_progress and not self.state.scenario.interruption_test:
            self._log(
                {
                    "event": "patient_response.held",
                    "reason": "agent_speech_in_progress",
                    "trigger": str(event.get("transcript", "")),
                }
            )
            return
        self._schedule_pending_patient_response()

    def _schedule_pending_patient_response(self) -> None:
        if self._pending_transcript_event is None:
            return

        if self._pending_response_task is not None:
            self._pending_response_task.cancel()
        loop_time = asyncio.get_running_loop().time()
        cooldown_delay = max(0.0, self._cooldown_until - loop_time)
        vad_delay = 0.0
        if (
            not self.state.scenario.interruption_test
            and self._last_agent_speech_stopped_at > 0.0
        ):
            elapsed_since_speech_stopped = loop_time - self._last_agent_speech_stopped_at
            vad_delay = max(
                0.0,
                POST_VAD_SILENCE_CONFIRMATION_SECONDS - elapsed_since_speech_stopped,
            )
        delay = (
            INTERRUPTION_RESPONSE_DELAY_SECONDS
            if self.state.scenario.interruption_test
            else DEFAULT_RESPONSE_DELAY_SECONDS
        )
        event = self._pending_transcript_event
        self._pending_transcript_event = None
        self._pending_response_task = asyncio.create_task(
            self._delayed_patient_response(event, max(delay, cooldown_delay, vad_delay))
        )

    async def _delayed_patient_response(self, event: dict[str, Any], delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            await self._maybe_create_patient_response(event)
        except asyncio.CancelledError:
            self._log({"event": "patient_response.cancelled", "reason": "agent_continued"})
            raise

    async def _handle_agent_speech_started(self, twilio_ws: WebSocket) -> None:
        self._agent_speech_in_progress = True
        self._pending_transcript_event = None
        if self._pending_response_task is not None:
            self._pending_response_task.cancel()
            self._pending_response_task = None

        if not self._bot_audio_in_progress:
            return

        if self.state.scenario.interruption_test:
            self._log({"event": "agent_speech_during_bot_audio", "action": "allowed_for_test"})
            return

        self._bot_audio_in_progress = False
        self._patient_response_in_progress = False
        self._log({"event": "agent_speech_during_bot_audio", "action": "yielded"})
        await self._send_openai(build_response_cancel())
        await twilio_ws.send_json(build_twilio_clear(self.state.stream_sid))

    def _handle_agent_speech_stopped(self) -> None:
        self._agent_speech_in_progress = False
        self._last_agent_speech_stopped_at = asyncio.get_running_loop().time()
        self._schedule_pending_patient_response()

    async def _maybe_create_patient_response(self, event: dict[str, Any]) -> None:
        transcript = str(event.get("transcript", "")).strip()
        if not transcript:
            self._log({"event": "patient_response.skipped", "reason": "empty_transcript"})
            return
        if self._already_responded_or_busy(event):
            return

        if not self._goal_introduced:
            if transcript_is_service_opening(transcript):
                self._goal_introduced = True
                await self._create_patient_response(
                    event,
                    build_opening_response(self.state.scenario),
                    {"event": "patient_response.goal_opening", "trigger": transcript},
                )
                return

            if transcript_is_ignorable_before_opening(transcript):
                self._log({"event": "patient_response.skipped", "reason": "pre_opening_ivr"})
                return

            if transcript_is_intake_before_goal(transcript):
                await self._create_patient_response(
                    event,
                    build_pre_goal_response(self.state.scenario, transcript),
                    {"event": "patient_response.pre_goal", "trigger": transcript},
                )
                return

            await self._create_patient_response(
                event,
                build_pre_goal_response(self.state.scenario, transcript),
                {"event": "patient_response.pre_goal", "trigger": transcript},
            )
            return

        if transcript_needs_more_agent_context(transcript):
            self._log({"event": "patient_response.skipped", "reason": "partial_agent_turn"})
            return

        if transcript_is_confusing_or_out_of_turn(self.state.scenario, transcript):
            await self._create_patient_response(
                event,
                build_confusion_response(self.state.scenario, transcript),
                {"event": "patient_response.confusion", "trigger": transcript},
            )
            return

        await self._create_patient_response(
            event,
            build_turn_response(self.state.scenario, transcript),
            {"event": "patient_response.turn", "trigger": transcript},
        )

    def _already_responded_or_busy(self, event: dict[str, Any]) -> bool:
        turn_key = build_agent_turn_key(event)
        if turn_key in self._responded_agent_turns:
            self._log({"event": "patient_response.skipped", "reason": "turn_already_answered"})
            return True
        if self._patient_response_in_progress:
            self._log({"event": "patient_response.skipped", "reason": "response_in_progress"})
            return True
        return False

    async def _create_patient_response(
        self,
        event: dict[str, Any],
        response: dict[str, Any],
        log_payload: dict[str, Any],
    ) -> None:
        turn_key = build_agent_turn_key(event)
        if turn_key in self._responded_agent_turns:
            self._log({"event": "patient_response.skipped", "reason": "turn_already_answered"})
            return
        if self._patient_response_in_progress:
            self._log({"event": "patient_response.skipped", "reason": "response_in_progress"})
            return

        self._responded_agent_turns.add(turn_key)
        self._patient_response_in_progress = True
        self._log(log_payload)
        await self._send_openai(response)

    def _finish_patient_response_cooldown(self) -> None:
        self._patient_response_in_progress = False
        self._cooldown_until = (
            asyncio.get_running_loop().time() + POST_RESPONSE_COOLDOWN_SECONDS
        )
