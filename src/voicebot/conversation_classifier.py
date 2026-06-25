"""Transcript classifiers and scenario completion evaluator."""

from __future__ import annotations

import re
from typing import Any

from voicebot.scenario_loader import Scenario


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


COMPLETION_CONFIRMATION_PHRASES = (
    "all set",
    "appointment is confirmed",
    "appointment has been confirmed",
    "appointment is scheduled",
    "appointment has been scheduled",
    "appointment is booked",
    "appointment has been booked",
    "booked you",
    "scheduled you",
    "confirmed you",
    "have you down",
    "got you down",
    "put you down",
    "you're scheduled",
    "you are scheduled",
    "you're booked",
    "you are booked",
    "you're confirmed",
    "you are confirmed",
)


COMPLETION_CLOSURE_PROMPTS = (
    "anything else",
    "any thing else",
    "anything more",
    "any other questions",
    "can i help you with anything else",
    "is there anything else",
    "will that be all",
    "does that work",
)


COMPLETION_INFORMATION_PHRASES = (
    "we are open",
    "we're open",
    "office hours",
    "hours are",
    "providers are",
    "doctor",
    "physician",
    "surgeon",
    "insurance",
    "accept",
    "cost",
    "copay",
    "wait time",
    "records",
    "medical records",
    "portal",
    "call 911",
    "emergency room",
    "er",
    "urgent care",
)


def new_patient_appointment_mismatch(
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


def transcript_asks_about_assumed_patient(transcript: str) -> bool:
    return bool(assumed_patient_name_parts(transcript))


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


def evaluate_scenario_completion(
    scenario: Scenario,
    conversation_turns: list[dict[str, str]],
    latest_agent_transcript: str,
) -> dict[str, Any] | None:
    latest = latest_agent_transcript.casefold()
    if not latest:
        return None

    agent_text = " ".join(
        turn["text"].casefold()
        for turn in conversation_turns
        if turn.get("speaker") == "agent"
    )
    if not agent_text:
        agent_text = latest

    if scenario_is_scheduling_like(scenario):
        if _agent_confirmed_appointment(agent_text, latest):
            return {
                "reason": "appointment_confirmed",
                "matched_text": latest_agent_transcript,
            }
        return None

    if _scenario_is_information_like(scenario):
        if _agent_provided_information(agent_text) and _agent_offered_closure(latest):
            return {
                "reason": "information_goal_answered",
                "matched_text": latest_agent_transcript,
            }
        return None

    if _agent_offered_closure(latest) and _agent_confirmed_goal_resolution(agent_text, latest):
        return {
            "reason": "scenario_goal_resolved",
            "matched_text": latest_agent_transcript,
        }
    return None


def scenario_is_scheduling_like(scenario: Scenario) -> bool:
    text = f"{scenario.goal} {scenario.success_criteria} {scenario.must_test}".casefold()
    return any(
        keyword in text
        for keyword in (
            "appointment",
            "schedule",
            "scheduled",
            "scheduling",
            "book",
            "reschedule",
            "cancel",
            "move an existing",
        )
    )


def _scenario_is_information_like(scenario: Scenario) -> bool:
    normalized_id = scenario.id.casefold()
    text = f"{scenario.goal} {scenario.success_criteria} {scenario.must_test}".casefold()
    return normalized_id.startswith("i-") or any(
        keyword in text
        for keyword in (
            "office hours",
            "who practices",
            "wait time",
            "insurance",
            "cost",
            "records",
            "information",
        )
    )


def _agent_confirmed_appointment(agent_text: str, latest: str) -> bool:
    has_confirmation = (
        any(phrase in agent_text for phrase in COMPLETION_CONFIRMATION_PHRASES)
        or any(
            phrase in agent_text or phrase in latest
            for phrase in (
                "appointment confirmed",
                "appointment cancelled",
                "appointment canceled",
                "appointment rescheduled",
                "cancelled your appointment",
                "canceled your appointment",
                "rescheduled your appointment",
            )
        )
    )
    if not has_confirmation:
        return False
    if _agent_offered_closure(latest):
        return True
    return _has_appointment_detail(latest) or _has_appointment_detail(agent_text)


def _agent_confirmed_goal_resolution(agent_text: str, latest: str) -> bool:
    return any(
        phrase in agent_text or phrase in latest
        for phrase in (
            "confirmed",
            "confirmation",
            "completed",
            "cancelled",
            "canceled",
            "rescheduled",
            "updated",
            "submitted",
            "sent",
        )
    )


def _agent_provided_information(agent_text: str) -> bool:
    return any(phrase in agent_text for phrase in COMPLETION_INFORMATION_PHRASES)


def _agent_offered_closure(latest: str) -> bool:
    return any(phrase in latest for phrase in COMPLETION_CLOSURE_PROMPTS)


def _has_appointment_detail(text: str) -> bool:
    return bool(
        re.search(
            r"\b("
            r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
            r"today|tomorrow|morning|afternoon|evening|"
            r"\d{1,2}(:\d{2})?\s?(am|pm)"
            r")\b",
            text,
        )
    )


def _contains_meta_disclosure_phrase(normalized_transcript: str, phrase: str) -> bool:
    if phrase in {"ai", "bot", "assistant"}:
        return re.search(rf"\b{re.escape(phrase)}\b", normalized_transcript) is not None
    return phrase in normalized_transcript


def _contains_meta_context_exemption(normalized_transcript: str) -> bool:
    return any(exemption in normalized_transcript for exemption in META_DISCLOSURE_CONTEXT_EXEMPTIONS)


def assumed_patient_name_parts(transcript: str) -> list[tuple[str, ...]]:
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
    if new_patient_appointment_mismatch(scenario, normalized):
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
