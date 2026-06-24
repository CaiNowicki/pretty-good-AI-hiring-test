"""Bridge Twilio Media Streams to the OpenAI Realtime API."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websockets
from starlette.websockets import WebSocket

from voicebot.artifacts import append_jsonl, utc_now_iso
from voicebot.config import Settings
from voicebot.scenario import Scenario, build_realtime_bootstrap, scenario_allows_meta_behavior


OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
PCMU_FORMAT = {"type": "audio/pcmu"}
DEFAULT_PREFIX_PADDING_MS = 500
DEFAULT_SILENCE_DURATION_MS = 450
DEFAULT_RESPONSE_DELAY_SECONDS = 0.0
POST_VAD_SILENCE_CONFIRMATION_SECONDS = 0.05
POST_RESPONSE_COOLDOWN_SECONDS = 0.25
LIMIT_WATCH_INTERVAL_SECONDS = 1.0
INTERRUPTION_PREFIX_PADDING_MS = 300
INTERRUPTION_SILENCE_DURATION_MS = 650
INTERRUPTION_RESPONSE_DELAY_SECONDS = 0.25
EMERGENCY_STOP_DTMF_DIGITS = {"9"}
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
    "part of pretty good ai",
    "para espanol",
    "para espa",
    "press",
    "oprima",
)
WAIT_FOR_AGENT_TO_CONTINUE_PHRASES = (
    "thanks for confirming",
    "specific provider you'd like to see or",
    "it looks",
    "for this demo",
    "for demo purposes",
    "for you",
)
CONFUSING_AGENT_PHRASES = (
    "dental purposes",
    "birthdate doesn't match",
    "date of birth doesn't match",
)
META_DISCLOSURE_PHRASES = (
    "test harness",
    "automated tester",
    "automated caller",
    "bot",
    "voice bot",
    "ai",
    "artificial intelligence",
    "assistant",
    "demo",
    "simulation",
    "simulated",
    "scenario",
    "evaluation",
    "benchmark",
    "testing",
    "a test",
)
META_DISCLOSURE_CONTEXT_EXEMPTIONS = (
    "pretty good ai",
    "part of pretty good ai",
)
ASSUMED_PATIENT_IDENTITY_PHRASES = (
    "am i speaking with",
    "am i speaking to",
    "are you",
    "is this",
    "speaking with",
    "speaking to",
    "calling for",
    "looking for",
)
ASSUMED_PATIENT_NAME_STOP_WORDS = {
    "a",
    "an",
    "about",
    "available",
    "bot",
    "calling",
    "for",
    "looking",
    "open",
    "patient",
    "the",
    "there",
    "this",
    "your",
}
NEW_PATIENT_CONSULTATION_ANSWERS = (
    "It's for a new patient consultation.",
    "This would be a new patient consultation.",
    "I'm trying to set up a new patient consultation.",
    "It should be a new patient consultation, not a follow-up.",
    "I'm a new patient, so I need a consultation appointment.",
)
NEW_PATIENT_EXISTING_APPOINTMENT_PHRASES = (
    "already have",
    "already scheduled",
    "appointment booked",
    "appointment on file",
    "appointment in our system",
)
NEW_PATIENT_CHANGE_APPOINTMENT_PHRASES = (
    "reschedule or cancel",
    "reschedule your appointment",
    "reschedule your current appointment",
    "cancel your current appointment",
    "change to your existing appointment",
    "change your existing appointment",
    "change the date or time",
)
NEW_PATIENT_EXISTING_APPOINTMENT_ANSWERS = (
    "Oh, I didn't realize there was already an appointment. Could you tell me when it is?",
    "I wasn't aware I had one scheduled. What date and time do you see for it?",
    "If there is already something booked, can you tell me the appointment date and time first?",
    "I thought I was calling to make a new appointment. What appointment is on file?",
)
NEW_PATIENT_CHANGE_APPOINTMENT_ANSWERS = (
    "Before I decide whether to reschedule or cancel, can you tell me what appointment is on file?",
    "I don't want to cancel anything until I know what appointment you see. When is it scheduled?",
    "Could you tell me the current appointment date and time before we change anything?",
    "I thought I needed a new appointment, so can you first tell me what is already scheduled?",
)
REPEATED_INFO_THRESHOLDS = (
    0.0,
    0.25,
    0.5,
    0.75,
    0.9,
)
REPEATED_INFO_LABELS = {
    "appointment_type": "the appointment type",
    "date_of_birth": "my date of birth",
    "first_name": "my first name",
    "full_name": "my name",
    "last_name": "my last name",
    "phone": "my phone number",
}
REPEATED_INFO_TEMPLATES = (
    "I already gave you {label}, but {answer}",
    "I mentioned {label} earlier, but {answer}",
    "I did give you {label} already. {answer}",
    "I've already shared {label}; {answer}",
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


def build_opening_response(scenario: Scenario, transcript: str = "") -> dict[str, Any]:
    meta_answer = build_meta_guardrail_answer(scenario, transcript)
    if meta_answer:
        instructions = f"Say only this exact patient answer: {meta_answer}"
        return {
            "type": "response.create",
            "response": {
                "instructions": instructions,
            },
        }

    assumed_identity_answer = build_assumed_patient_identity_answer(
        scenario,
        transcript,
        include_opening=True,
    )
    if assumed_identity_answer:
        instructions = f"Say only this exact patient answer: {assumed_identity_answer}"
    else:
        instructions = (
            "Say this opening line exactly once, naturally, then wait for the agent: "
            f"{scenario.opening_line}"
        )

    return {
        "type": "response.create",
        "response": {
            "instructions": instructions,
        },
    }


def build_turn_response(scenario: Scenario | None = None, transcript: str = "") -> dict[str, Any]:
    meta_answer = build_meta_guardrail_answer(scenario, transcript)
    if meta_answer:
        instructions = f"Say only this exact patient answer: {meta_answer}"
    else:
        exact_answer = build_exact_fact_answer(scenario, transcript) if scenario is not None else ""
        if exact_answer:
            instructions = f"Say only this exact patient answer: {exact_answer}"
        else:
            instructions = (
                "Respond now as the patient for the current call turn. Keep it short, "
                "answer only what was asked, use the "
                "scenario facts exactly, do not add unrelated preferences or comments, "
                "do not mention tests, harnesses, bots, assistants, simulations, or "
                "demos, and wait for the agent after speaking."
            )

    return {
        "type": "response.create",
        "response": {
            "instructions": instructions,
        },
    }


def build_pre_goal_response(scenario: Scenario | None = None, transcript: str = "") -> dict[str, Any]:
    meta_answer = build_meta_guardrail_answer(scenario, transcript)
    if meta_answer:
        instructions = f"Say only this exact patient answer: {meta_answer}"
    else:
        exact_answer = build_exact_fact_answer(scenario, transcript) if scenario is not None else ""
        if exact_answer:
            instructions = f"Say only this exact patient answer: {exact_answer}"
        else:
            instructions = (
                "Answer the agent's intake or profile setup question directly as the patient. "
                "Do not ask to schedule yet, do not repeat the opening line, use the scenario "
                "facts exactly, do not add unrelated preferences or comments, do not mention "
                "tests, harnesses, bots, assistants, simulations, or demos, and keep it brief."
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


def build_assumed_patient_identity_answer(
    scenario: Scenario | None,
    transcript: str,
    *,
    include_opening: bool = False,
) -> str:
    if scenario is None or not transcript_asks_about_assumed_patient(transcript):
        return ""

    caller_name = _caller_full_name(scenario)
    patient_name = scenario.facts.get("patient_name", "").strip()
    first_name = _caller_first_name(scenario)
    if _scenario_identity_matches_assumed_patient(scenario, transcript):
        if _scenario_is_new_patient(scenario):
            answer = f"Oh, yes, this is {first_name}. I'm surprised you had that already."
            if include_opening:
                return f"{answer} {scenario.opening_line}"
            return answer
        if include_opening:
            return f"Yes, this is {first_name}. {scenario.opening_line}"
        return f"Yes, this is {first_name}."

    correction_name = caller_name or patient_name
    if caller_name and patient_name and patient_name.casefold() not in caller_name.casefold():
        return (
            f"No, this is {caller_name}, calling for {patient_name}. "
            "I think you may have the wrong patient."
        )
    if correction_name:
        return f"No, this is {correction_name}. I think you may have the wrong patient."
    return "No, I think you may have the wrong patient."


def build_meta_guardrail_answer(scenario: Scenario | None, transcript: str) -> str:
    if scenario is not None and scenario_allows_meta_behavior(scenario):
        return ""
    if not transcript_asks_about_meta_behavior(transcript):
        return ""
    return "I'm just calling as a patient about my appointment."


def build_exact_fact_answer(scenario: Scenario | None, transcript: str) -> str:
    if scenario is None:
        return ""

    normalized = transcript.casefold()
    goal = scenario.goal.casefold()
    full_name = _caller_full_name(scenario)
    first_name = _caller_first_name(scenario)
    last_name = _caller_last_name(scenario)

    assumed_identity_answer = build_assumed_patient_identity_answer(scenario, transcript)
    if assumed_identity_answer:
        return assumed_identity_answer
    if "date of birth" in normalized or "birthdate" in normalized or "dob" in normalized:
        dob = scenario.facts.get("date_of_birth", "").strip()
        return f"My date of birth is {dob}." if dob else ""
    if _asks_to_confirm_known_date_of_birth(scenario, transcript, normalized):
        dob = scenario.facts.get("date_of_birth", "").strip()
        return f"Yes, my date of birth is {dob}." if dob else ""
    if _asks_about_full_name(normalized) and full_name:
        return full_name
    if "first name" in normalized and first_name:
        return first_name
    if "last name" in normalized and last_name:
        return last_name
    if "your name" in normalized and full_name:
        return full_name
    if "phone" in normalized:
        phone = scenario.facts.get("phone", "").strip()
        return phone
    if _asks_about_appointment_type(normalized):
        if "new patient consultation" in goal:
            return _select_stable_variant(
                NEW_PATIENT_CONSULTATION_ANSWERS,
                scenario.id,
                transcript,
            )
        if "routine visit" in goal:
            return "It's a routine visit."
        if "reschedule" in goal or "move an existing appointment" in goal:
            return "I'm calling to reschedule an existing appointment."
        if "cancel" in goal:
            return "I'm calling to cancel an appointment."
    return ""


def requested_info_key(scenario: Scenario | None, transcript: str) -> str:
    if scenario is None:
        return ""

    normalized = transcript.casefold()
    if "date of birth" in normalized or "birthdate" in normalized or "dob" in normalized:
        return "date_of_birth"
    if _asks_to_confirm_known_date_of_birth(scenario, transcript, normalized):
        return "date_of_birth"
    if _asks_about_full_name(normalized) or "your name" in normalized:
        return "full_name"
    if "first name" in normalized:
        return "first_name"
    if "last name" in normalized:
        return "last_name"
    if "phone" in normalized:
        return "phone"
    if _asks_about_appointment_type(normalized):
        return "appointment_type"
    return ""


def repeated_info_probability(repeat_count: int) -> float:
    if repeat_count < 0:
        return 0.0
    if repeat_count < len(REPEATED_INFO_THRESHOLDS):
        return REPEATED_INFO_THRESHOLDS[repeat_count]
    return REPEATED_INFO_THRESHOLDS[-1]


def should_point_out_repeated_info(repeat_count: int, random_value: float) -> bool:
    probability = repeated_info_probability(repeat_count)
    return random_value < probability


def build_repeated_info_answer(
    info_key: str,
    exact_answer: str,
    template_index: int,
) -> str:
    label = REPEATED_INFO_LABELS.get(info_key, "that information")
    template = REPEATED_INFO_TEMPLATES[template_index % len(REPEATED_INFO_TEMPLATES)]
    return template.format(label=label, answer=exact_answer)


def _caller_full_name(scenario: Scenario) -> str:
    return scenario.facts.get("full_name", scenario.facts.get("name", "")).strip()


def _select_stable_variant(options: tuple[str, ...], *keys: str) -> str:
    if not options:
        return ""
    digest = hashlib.sha256("|".join(keys).encode("utf-8")).digest()
    return options[int.from_bytes(digest[:2], "big") % len(options)]


def _caller_first_name(scenario: Scenario) -> str:
    first_name = scenario.facts.get("first_name", "").strip()
    if first_name:
        return first_name
    name_parts = _caller_full_name(scenario).split()
    return name_parts[0] if name_parts else ""


def _caller_last_name(scenario: Scenario) -> str:
    last_name = scenario.facts.get("last_name", "").strip()
    if last_name:
        return last_name
    name_parts = _caller_full_name(scenario).split()
    return name_parts[-1] if len(name_parts) > 1 else ""


def _asks_about_full_name(normalized_transcript: str) -> bool:
    return (
        "full name" in normalized_transcript
        or "first and last" in normalized_transcript
        or "first name and last name" in normalized_transcript
    )


def _asks_to_confirm_known_date_of_birth(
    scenario: Scenario,
    transcript: str,
    normalized_transcript: str,
) -> bool:
    if "?" not in transcript:
        return False

    dob = scenario.facts.get("date_of_birth", "").strip()
    if not dob:
        return False

    dob_tokens = re.findall(r"[a-z]+|\d+", dob.casefold())
    transcript_tokens = set(re.findall(r"[a-z]+|\d+", normalized_transcript))
    return any(token in transcript_tokens for token in dob_tokens)


def build_confusion_reply(scenario: Scenario, transcript: str) -> str:
    normalized = transcript.casefold()

    if "birthdate doesn't match" in normalized or "date of birth doesn't match" in normalized:
        dob = scenario.facts.get("date_of_birth", "").strip()
        return f"I don't understand. My date of birth is {dob}." if dob else "I don't understand."

    if "dental" in normalized:
        return "I don't understand; I thought I called orthopedics."

    new_patient_mismatch = _new_patient_appointment_mismatch(scenario, normalized)
    if new_patient_mismatch == "existing":
        return _select_stable_variant(
            NEW_PATIENT_EXISTING_APPOINTMENT_ANSWERS,
            scenario.id,
            transcript,
        )
    if new_patient_mismatch == "change":
        return _select_stable_variant(
            NEW_PATIENT_CHANGE_APPOINTMENT_ANSWERS,
            scenario.id,
            transcript,
        )

    return "I don't understand what you mean."


def _new_patient_appointment_mismatch(
    scenario: Scenario,
    normalized_transcript: str,
) -> str:
    if "new patient" not in scenario.goal.casefold():
        return ""
    if any(phrase in normalized_transcript for phrase in NEW_PATIENT_CHANGE_APPOINTMENT_PHRASES):
        return "change"
    if any(
        phrase in normalized_transcript
        for phrase in NEW_PATIENT_EXISTING_APPOINTMENT_PHRASES
    ):
        return "existing"
    return ""


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


def transcript_asks_about_assumed_patient(transcript: str) -> bool:
    return bool(_assumed_patient_name_parts(transcript))


def transcript_asks_about_meta_behavior(transcript: str) -> bool:
    normalized = transcript.casefold()
    if _contains_meta_context_exemption(normalized):
        return any(
            _contains_meta_disclosure_phrase(normalized, phrase)
            for phrase in META_DISCLOSURE_PHRASES
            if phrase not in {"ai"}
        )
    return any(_contains_meta_disclosure_phrase(normalized, phrase) for phrase in META_DISCLOSURE_PHRASES)


def transcript_requests_emergency_stop(transcript: str, phrases: list[str]) -> bool:
    normalized = transcript.casefold()
    return any(phrase.casefold() in normalized for phrase in phrases)


def _contains_meta_disclosure_phrase(normalized_transcript: str, phrase: str) -> bool:
    if phrase in {"ai", "bot", "assistant"}:
        return re.search(rf"\b{re.escape(phrase)}\b", normalized_transcript) is not None
    return phrase in normalized_transcript


def _contains_meta_context_exemption(normalized_transcript: str) -> bool:
    return any(exemption in normalized_transcript for exemption in META_DISCLOSURE_CONTEXT_EXEMPTIONS)


def _assumed_patient_name_parts(transcript: str) -> list[tuple[str, ...]]:
    normalized = transcript.casefold()
    assumed_names: list[tuple[str, ...]] = []
    for phrase in ASSUMED_PATIENT_IDENTITY_PHRASES:
        match = re.search(rf"\b{re.escape(phrase)}\b\s*", normalized)
        if match is None:
            continue
        remainder = re.split(r"[.?!,;:]", normalized[match.end() :], maxsplit=1)[0]
        words = re.findall(r"[a-z]+", remainder)
        if not words or words[0] in ASSUMED_PATIENT_NAME_STOP_WORDS:
            continue
        assumed_names.append(tuple(words[:2]))
    return assumed_names


def _scenario_identity_matches_assumed_patient(scenario: Scenario, transcript: str) -> bool:
    identity_values = [
        _caller_full_name(scenario),
        _caller_first_name(scenario),
        _caller_last_name(scenario),
        scenario.facts.get("patient_name", ""),
    ]
    assumed_names = _assumed_patient_name_parts(transcript)
    for value in identity_values:
        identity_parts = tuple(re.findall(r"[a-z]+", value.casefold()))
        for assumed_parts in assumed_names:
            if identity_parts[: len(assumed_parts)] == assumed_parts:
                return True
    return False


def _scenario_is_new_patient(scenario: Scenario) -> bool:
    searchable_text = " ".join(
        [
            scenario.goal,
            scenario.opening_line,
            scenario.facts.get("patient_status", ""),
        ]
    ).casefold()
    return "new patient" in searchable_text


def transcript_is_service_opening(transcript: str) -> bool:
    normalized = transcript.casefold()
    return any(phrase in normalized for phrase in AGENT_SERVICE_OPENING_PHRASES)


def transcript_is_intake_before_goal(transcript: str) -> bool:
    normalized = transcript.casefold()
    return any(phrase in normalized for phrase in INTAKE_BEFORE_GOAL_PHRASES)


def transcript_is_ignorable_before_opening(transcript: str) -> bool:
    if transcript_asks_about_assumed_patient(transcript):
        return False
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
    if _new_patient_appointment_mismatch(scenario, normalized):
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
        self._limit_watch_task: asyncio.Task[None] | None = None
        self._pending_transcript_event: dict[str, Any] | None = None
        self._agent_speech_in_progress = False
        self._last_agent_speech_stopped_at = 0.0
        self._call_started_at = 0.0
        self._last_conversation_activity_at = 0.0
        self._goal_introduced = False
        self._bot_audio_in_progress = False
        self._patient_response_in_progress = False
        self._cooldown_until = 0.0
        self._stop_requested = False
        self._agent_turn_count = 0
        self._counted_agent_turns: set[str] = set()
        self._responded_agent_turns: set[str] = set()
        self._provided_info_counts: dict[str, int] = {}
        self._last_repeated_info_template_index: dict[str, int] = {}
        self._random = random.Random()

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
        loop_time = asyncio.get_running_loop().time()
        self._call_started_at = loop_time
        self._last_conversation_activity_at = loop_time
        self._openai_to_twilio_task = asyncio.create_task(self._pipe_openai_to_twilio(twilio_ws))
        self._limit_watch_task = asyncio.create_task(self._watch_deterministic_limits(twilio_ws))
        self._log(
            {
                "event": "realtime.started",
                "scenario_id": self.state.scenario.id,
                "stream_sid": self.state.stream_sid,
                "limits": self.state.scenario.limits.to_dict(),
            }
        )

    async def forward_twilio_media(self, payload: str) -> None:
        if self._stop_requested or self._openai_ws is None or not payload:
            return
        await self._send_openai(build_input_audio_append(payload))

    async def request_emergency_stop(self, twilio_ws: WebSocket, reason: str) -> None:
        await self._terminate_call(twilio_ws, "emergency_stop", {"reason": reason})

    async def close(self) -> None:
        if self._limit_watch_task is not None:
            task = self._limit_watch_task
            self._limit_watch_task = None
            if task is not asyncio.current_task():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
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
            if self._stop_requested:
                break
            event = json.loads(raw_message)
            event_type = event.get("type", "unknown")

            if event_type == "response.output_audio.delta":
                self._mark_conversation_activity()
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
                if await self._stop_if_transcript_hits_hard_limit(twilio_ws, event):
                    break
                self._schedule_patient_response(event)

            if event_type == "input_audio_buffer.speech_started":
                self._mark_conversation_activity()
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

    def _mark_conversation_activity(self) -> None:
        self._last_conversation_activity_at = asyncio.get_running_loop().time()

    async def _watch_deterministic_limits(self, twilio_ws: WebSocket) -> None:
        while not self._stop_requested:
            await asyncio.sleep(LIMIT_WATCH_INTERVAL_SECONDS)
            if self._call_started_at <= 0.0 or self._last_conversation_activity_at <= 0.0:
                continue

            now = asyncio.get_running_loop().time()
            limits = self.state.scenario.limits
            elapsed = now - self._call_started_at
            silence = now - self._last_conversation_activity_at
            if elapsed >= limits.max_call_seconds:
                await self._terminate_call(
                    twilio_ws,
                    "max_call_duration",
                    {
                        "elapsed_seconds": round(elapsed, 3),
                        "max_call_seconds": limits.max_call_seconds,
                    },
                )
                return
            if silence >= limits.max_silence_seconds:
                await self._terminate_call(
                    twilio_ws,
                    "max_silence",
                    {
                        "silence_seconds": round(silence, 3),
                        "max_silence_seconds": limits.max_silence_seconds,
                    },
                )
                return

    async def _stop_if_transcript_hits_hard_limit(
        self,
        twilio_ws: WebSocket,
        event: dict[str, Any],
    ) -> bool:
        self._mark_conversation_activity()
        transcript = str(event.get("transcript", "")).strip()
        if transcript_requests_emergency_stop(
            transcript,
            self.state.scenario.limits.emergency_stop_phrases,
        ):
            await self._terminate_call(
                twilio_ws,
                "emergency_stop_phrase",
                {"trigger": transcript},
            )
            return True

        turn_key = build_agent_turn_key(event)
        if turn_key in self._counted_agent_turns:
            return False
        self._counted_agent_turns.add(turn_key)
        self._agent_turn_count += 1
        if self._agent_turn_count <= self.state.scenario.limits.max_turns:
            return False

        await self._terminate_call(
            twilio_ws,
            "max_turns",
            {
                "turn_count": self._agent_turn_count,
                "max_turns": self.state.scenario.limits.max_turns,
            },
        )
        return True

    async def _terminate_call(
        self,
        twilio_ws: WebSocket | None,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self._stop_requested:
            return
        self._stop_requested = True
        self._log(
            {
                "event": "call.stop_requested",
                "reason": reason,
                "details": details or {},
                "limits": self.state.scenario.limits.to_dict(),
            }
        )
        if self._pending_response_task is not None:
            self._pending_response_task.cancel()
            self._pending_response_task = None
        self._pending_transcript_event = None
        self._patient_response_in_progress = False
        self._bot_audio_in_progress = False

        if self._openai_ws is not None:
            with contextlib.suppress(Exception):
                await self._send_openai(build_response_cancel())
            with contextlib.suppress(Exception):
                await self._openai_ws.close()
            self._openai_ws = None

        if twilio_ws is not None:
            with contextlib.suppress(Exception):
                await twilio_ws.send_json(build_twilio_clear(self.state.stream_sid))
            with contextlib.suppress(Exception):
                await twilio_ws.close(code=1000)

    def _schedule_patient_response(self, event: dict[str, Any]) -> None:
        if self._stop_requested:
            return
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
        if self._stop_requested:
            return
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
            if self._stop_requested:
                return
            await self._maybe_create_patient_response(event)
        except asyncio.CancelledError:
            self._log({"event": "patient_response.cancelled", "reason": "agent_continued"})
            raise

    async def _handle_agent_speech_started(self, twilio_ws: WebSocket) -> None:
        if self._stop_requested:
            return
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
        if self._stop_requested:
            return
        self._agent_speech_in_progress = False
        self._last_agent_speech_stopped_at = asyncio.get_running_loop().time()
        self._schedule_pending_patient_response()

    async def _maybe_create_patient_response(self, event: dict[str, Any]) -> None:
        if self._stop_requested:
            return
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
                    build_opening_response(self.state.scenario, transcript),
                    {"event": "patient_response.goal_opening", "trigger": transcript},
                )
                return

            if transcript_is_ignorable_before_opening(transcript):
                self._log({"event": "patient_response.skipped", "reason": "pre_opening_ivr"})
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

            if transcript_is_intake_before_goal(transcript):
                await self._create_patient_response(
                    event,
                    self._build_stateful_patient_response(event, pre_goal=True),
                    {"event": "patient_response.pre_goal", "trigger": transcript},
                )
                return

            await self._create_patient_response(
                event,
                self._build_stateful_patient_response(event, pre_goal=True),
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
            self._build_stateful_patient_response(event, pre_goal=False),
            {"event": "patient_response.turn", "trigger": transcript},
        )

    def _build_stateful_patient_response(
        self,
        event: dict[str, Any],
        *,
        pre_goal: bool,
    ) -> dict[str, Any]:
        transcript = str(event.get("transcript", "")).strip()
        meta_answer = build_meta_guardrail_answer(self.state.scenario, transcript)
        if meta_answer:
            if pre_goal:
                return build_pre_goal_response(self.state.scenario, transcript)
            return build_turn_response(self.state.scenario, transcript)

        info_key = requested_info_key(self.state.scenario, transcript)
        exact_answer = build_exact_fact_answer(self.state.scenario, transcript)
        if info_key and exact_answer:
            repeat_count = self._provided_info_counts.get(info_key, 0)
            answer = exact_answer
            if should_point_out_repeated_info(repeat_count, self._random.random()):
                answer = self._build_repeated_info_answer(info_key, exact_answer)
            self._provided_info_counts[info_key] = repeat_count + 1
            return {
                "type": "response.create",
                "response": {"instructions": f"Say only this exact patient answer: {answer}"},
            }

        if pre_goal:
            return build_pre_goal_response(self.state.scenario, transcript)
        return build_turn_response(self.state.scenario, transcript)

    def _build_repeated_info_answer(self, info_key: str, exact_answer: str) -> str:
        previous_index = self._last_repeated_info_template_index.get(info_key)
        template_count = len(REPEATED_INFO_TEMPLATES)
        template_index = self._random.randrange(template_count)
        if previous_index is not None and template_count > 1:
            offset = self._random.randrange(template_count - 1)
            template_index = (previous_index + 1 + offset) % template_count
        self._last_repeated_info_template_index[info_key] = template_index
        return build_repeated_info_answer(info_key, exact_answer, template_index)

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
        if self._stop_requested:
            return
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
