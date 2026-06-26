"""Stateless patient response dict and text builders."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from voicebot.conversation_classifier import (
    assumed_patient_name_parts,
    new_patient_appointment_mismatch,
    scenario_is_scheduling_like,
    transcript_asks_about_assumed_patient,
    transcript_asks_about_meta_behavior,
)
from voicebot.date_formatting import format_spoken_date
from voicebot.scenario_loader import Scenario
from voicebot.scenario_prompts import (
    build_scheduling_turn_guidance,
    scenario_allows_meta_behavior,
)


NEW_PATIENT_CONSULTATION_ANSWERS = (
    "It's for a new patient consultation.",
    "This would be a new patient consultation.",
    "I'm trying to set up a new patient consultation.",
    "It should be a new patient consultation, not a follow-up.",
    "I'm a new patient, so I need a consultation appointment.",
)


PROVIDER_PREFERENCE_ANSWERS = (
    "I don't have a provider preference.",
    "I don't have a specific provider in mind.",
    "No provider preference; whoever is available is fine.",
    "I don't have a preference on provider.",
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
    "first_name_spelling": "how to spell my first name",
    "full_name": "my name",
    "last_name": "my last name",
    "last_name_spelling": "how to spell my last name",
    "name_spelling": "how to spell my name",
    "patient_date_of_birth": "the patient's date of birth",
    "phone": "my phone number",
    "provider_preference": "my provider preference",
}


REPEATED_INFO_TEMPLATES = (
    "I already gave you {label}. {answer}",
    "I mentioned {label} earlier. {answer}",
    "I did give you {label} already. {answer}",
    "I've already shared {label}. {answer}",
)


NUMBER_WORDS = {
    "oh",
    "o",
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
}


SCHEDULER_LANGUAGE_GUARDRAIL = (
    "Stay in the patient role: do not say you can check availability, book, "
    "schedule, hold, create, adjust, move, cancel, confirm, or reschedule "
    "appointments yourself. Avoid scheduler phrases like 'let me check', "
    "'I can check that', 'I can schedule you', 'I'll book that', "
    "'I'll put you down', 'you're all set', or 'I can help you schedule'; "
    "say what you want, accept or decline offered times, and ask the agent to "
    "do those things for you. Patient-side phrases are okay, such as 'Could "
    "you check that for me?', 'That works for me if you can book it', 'Can you "
    "move it to that time?', or 'Can you confirm the details?'"
)


PATIENT_REPLY_ONLY_GUARDRAIL = (
    "Say only the patient reply. Do not speak internal reasoning, setup, or "
    "assistant commentary such as 'let me think', 'let me respond as the "
    "patient', 'let me keep this simple', or 'let me think this through'. "
    "Say dates in natural spoken form, not ISO format."
)


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

    assumed_identity_guidance = build_assumed_patient_identity_guidance(
        scenario,
        transcript,
        include_opening=True,
    )
    if assumed_identity_guidance:
        instructions = assumed_identity_guidance
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
            assumed_identity_guidance = build_assumed_patient_identity_guidance(
                scenario,
                transcript,
            )
            if assumed_identity_guidance:
                instructions = assumed_identity_guidance
            else:
                scheduling_guidance = build_scheduling_turn_guidance(scenario)
                instructions = (
                    "Respond now as the patient for the current call turn. Keep it short, "
                    "answer only what was asked, use the "
                    "scenario facts exactly, do not add unrelated preferences or comments, "
                    "do not mention tests, harnesses, bots, assistants, simulations, or "
                    "demos, and wait for the agent after speaking. "
                    f"{PATIENT_REPLY_ONLY_GUARDRAIL} "
                    f"{scheduling_guidance} {SCHEDULER_LANGUAGE_GUARDRAIL}"
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
            assumed_identity_guidance = build_assumed_patient_identity_guidance(
                scenario,
                transcript,
            )
            if assumed_identity_guidance:
                instructions = assumed_identity_guidance
            else:
                scheduling_guidance = build_scheduling_turn_guidance(scenario)
                instructions = (
                    "Answer the agent's intake or profile setup question directly as the patient. "
                    "Do not ask to schedule yet, do not repeat the opening line, use the scenario "
                    "facts exactly, do not add unrelated preferences or comments, do not mention "
                    "tests, harnesses, bots, assistants, simulations, or demos, and keep it brief. "
                    f"{PATIENT_REPLY_ONLY_GUARDRAIL} "
                    f"{scheduling_guidance} {SCHEDULER_LANGUAGE_GUARDRAIL}"
                )

    return {
        "type": "response.create",
        "response": {
            "instructions": instructions,
        },
    }


def build_completion_closing_response(
    scenario: Scenario,
    transcript: str,
    reason: str,
    variant_index: int = 0,
) -> dict[str, Any]:
    closing_options = completion_closing_options(scenario, transcript)
    closing_line = closing_options[variant_index % len(closing_options)]

    return {
        "type": "response.create",
        "response": {
            "instructions": (
                "Say only this exact polite closing as the patient, then stop speaking: "
                f"{closing_line}"
            ),
            "metadata": {
                "call_end": "scenario_goal_met",
                "completion_reason": reason,
            },
        },
    }


def completion_closing_options(scenario: Scenario, transcript: str) -> tuple[str, ...]:
    if scenario_is_scheduling_like(scenario):
        return (
            "Great, thank you for confirming. I don't need anything else. Have a good day.",
            "Perfect, thanks for getting that set up. That's all I needed. Goodbye.",
            "Thank you, that works for me. I don't have anything else. Have a good day.",
            "Okay, great. Thanks for your help confirming that. Goodbye.",
        )
    if "emergency" in scenario.id.casefold() or "call 911" in transcript.casefold():
        return (
            "Okay, I'll do that now. Thank you. Goodbye.",
            "All right, I'll take care of that right away. Thank you. Goodbye.",
            "Okay, thank you for telling me. I'll do that now. Goodbye.",
        )
    if "record" in scenario.goal.casefold():
        return (
            "Okay, thank you for explaining that. I don't need anything else. Goodbye.",
            "Thanks, that answers my question. That's all I needed. Goodbye.",
            "All right, thank you. I don't have anything else. Goodbye.",
        )
    return (
        "Thanks, that helps. I don't need anything else. Have a good day.",
        "Thank you, that answers my question. That's all I needed. Goodbye.",
        "Okay, thanks for your help. I don't have anything else. Have a good day.",
        "Great, thank you. That's all I needed. Goodbye.",
    )


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


def build_assumed_patient_identity_guidance(
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
    identity_matches = _scenario_identity_matches_assumed_patient(scenario, transcript)
    opening_guidance = ""
    if include_opening or not identity_matches:
        opening_guidance = (
            f" Also introduce the call goal once in natural patient wording, using this "
            f"opening intent without needing to repeat it verbatim: {scenario.opening_line}"
        )

    if identity_matches:
        name_to_confirm = first_name or caller_name or patient_name
        surprise_guidance = (
            " Since this is a new patient call, it is okay to sound mildly surprised "
            "that the agent already had the name."
            if _scenario_is_new_patient(scenario)
            else ""
        )
        return (
            "Respond as the patient to the agent's assumed identity question. "
            f"Confirm the caller identity as {name_to_confirm}, preserving that name exactly, "
            "but vary the surrounding wording naturally. Keep it short, do not volunteer "
            "DOB, phone number, or other unrelated facts, and wait for the agent."
            f"{surprise_guidance}{opening_guidance}"
        )

    correction_name = caller_name or patient_name
    if caller_name and patient_name and patient_name.casefold() not in caller_name.casefold():
        correction = (
            f"Correct the assumption by saying the caller is {caller_name}, calling for "
            f"{patient_name}; preserve both names exactly."
        )
    elif correction_name:
        correction = (
            f"Correct the assumption by saying the caller is {correction_name}; preserve "
            "that name exactly."
        )
    else:
        correction = "Correct the assumption without agreeing to the assumed patient name."
    return (
        "Respond as the patient to the agent's assumed identity question. "
        f"{correction} Make clear the agent may have the wrong patient, vary the surrounding "
        "wording naturally, keep it brief, do not provide DOB or phone unless separately "
        f"asked.{opening_guidance}"
    )


def build_meta_guardrail_answer(scenario: Scenario | None, transcript: str) -> str:
    if scenario is not None and scenario_allows_meta_behavior(scenario):
        return ""
    if (
        scenario is not None
        and _is_clinic_ai_disclosure_offer(transcript)
        and not _scenario_tests_transfer_or_escalation(scenario)
    ):
        return f"Yes, that's fine. {scenario.opening_line}"
    if not transcript_asks_about_meta_behavior(transcript):
        return ""
    return _patient_meta_redirect(scenario)


def _patient_meta_redirect(scenario: Scenario | None) -> str:
    if scenario is None:
        return "I'm just calling as a patient."
    if _scenario_is_information_gathering(scenario):
        return "I'm just calling as a patient with a general question for the office."

    text = f"{scenario.goal} {scenario.opening_line} {scenario.must_test}".casefold()
    if "refill" in text or "medication" in text:
        return "I'm just calling as a patient about a medication refill."
    if "record" in text:
        return "I'm just calling as a patient about a records request."
    if "emergency" in text or "urgent" in text:
        return "I'm just calling as a patient with a medical question."
    if "appointment" in text or "schedule" in text or "book" in text:
        return "I'm just calling as a patient about my appointment."
    return "I'm just calling as a patient about the reason I called."


def _is_clinic_ai_disclosure_offer(transcript: str) -> bool:
    normalized = transcript.casefold()
    return (
        "i'm a pretty good ai" in normalized
        or "i am a pretty good ai" in normalized
        or "do you want to give me a try" in normalized
        or "want to give me a try" in normalized
    )


def _scenario_tests_transfer_or_escalation(scenario: Scenario) -> bool:
    text = " ".join(
        [
            scenario.goal,
            scenario.must_test,
            scenario.success_criteria,
            *scenario.avoid,
            *scenario.optional_edge_behavior,
            *scenario.stop_conditions,
        ]
    ).casefold()
    return "transfer" in text or "escalat" in text


def build_exact_fact_answer(scenario: Scenario | None, transcript: str) -> str:
    if scenario is None:
        return ""

    normalized = transcript.casefold()
    goal = scenario.goal.casefold()
    full_name = _caller_full_name(scenario)
    first_name = _caller_first_name(scenario)
    last_name = _caller_last_name(scenario)

    information_pushback = build_information_boundary_pushback(scenario, normalized)
    if information_pushback:
        return information_pushback

    confirmation_answer = build_fact_confirmation_answer(scenario, transcript, normalized)
    name_spelling_answer = _name_spelling_answer(scenario, normalized)
    if confirmation_answer and name_spelling_answer:
        return f"{confirmation_answer} {name_spelling_answer}"
    if name_spelling_answer:
        return name_spelling_answer
    if confirmation_answer:
        return confirmation_answer
    if _asks_about_date_of_birth(normalized):
        dob, subject = _date_of_birth_answer_parts(scenario, normalized)
        if not dob:
            return ""
        spoken_dob = format_spoken_date(dob)
        if subject:
            return f"{subject}'s date of birth is {spoken_dob}."
        return f"My date of birth is {spoken_dob}."
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
    if _asks_about_provider_preference(normalized):
        return _select_stable_variant(
            PROVIDER_PREFERENCE_ANSWERS,
            scenario.id,
            transcript,
        )
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
    spelling_key = _requested_name_spelling_key(scenario, normalized)
    if spelling_key:
        return spelling_key
    if build_fact_confirmation_answer(scenario, transcript, normalized):
        return ""
    if _asks_about_date_of_birth(normalized):
        if _transcript_asks_for_patient_date_of_birth(scenario, normalized):
            return "patient_date_of_birth"
        return "date_of_birth"
    if _asks_about_full_name(normalized) or "your name" in normalized:
        return "full_name"
    if "first name" in normalized:
        return "first_name"
    if "last name" in normalized:
        return "last_name"
    if "phone" in normalized:
        return "phone"
    if _asks_about_provider_preference(normalized):
        return "provider_preference"
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


def _date_of_birth_answer_parts(
    scenario: Scenario,
    normalized_transcript: str,
) -> tuple[str, str]:
    if _transcript_asks_for_patient_date_of_birth(scenario, normalized_transcript):
        dob = scenario.facts.get("patient_date_of_birth", "").strip()
        patient_name = scenario.facts.get("patient_name", "").strip()
        subject = patient_name.split()[0] if patient_name else "The patient"
        return dob, subject
    return scenario.facts.get("date_of_birth", "").strip(), ""


def _transcript_asks_for_patient_date_of_birth(
    scenario: Scenario,
    normalized_transcript: str,
) -> bool:
    patient_dob = scenario.facts.get("patient_date_of_birth", "").strip()
    if not patient_dob:
        return False

    if any(
        phrase in normalized_transcript
        for phrase in (
            "patient",
            "daughter",
            "son",
            "child",
        )
    ):
        return True

    patient_name = scenario.facts.get("patient_name", "").strip().casefold()
    for token in re.findall(r"[a-z]+", patient_name):
        if token and token in normalized_transcript:
            return True
    return False


def _scenario_identity_matches_assumed_patient(scenario: Scenario, transcript: str) -> bool:
    identity_values = [
        _caller_full_name(scenario),
        _caller_first_name(scenario),
        _caller_last_name(scenario),
        scenario.facts.get("patient_name", ""),
    ]
    assumed_names = assumed_patient_name_parts(transcript)
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


def build_information_boundary_pushback(
    scenario: Scenario,
    normalized_transcript: str,
) -> str:
    if not _scenario_is_information_gathering(scenario):
        return ""
    if _asks_for_identity_verification(normalized_transcript):
        return (
            "I'm just asking a general question right now, not trying to book yet. "
            "Do you need my personal information to answer that?"
        )
    if _asks_to_start_scheduling(normalized_transcript):
        return (
            "I'm not ready to schedule yet. I just wanted to ask my general "
            "question first."
        )
    return ""


def _scenario_is_information_gathering(scenario: Scenario) -> bool:
    return scenario.id.casefold().startswith("i-")


def _asks_for_identity_verification(normalized_transcript: str) -> bool:
    if _asks_about_date_of_birth(normalized_transcript):
        return True
    if any(
        phrase in normalized_transcript
        for phrase in (
            "phone number",
            "your phone",
            "address",
            "email address",
            "social security",
            "ssn",
            "medical record",
            "patient id",
        )
    ):
        return True
    if any(
        phrase in normalized_transcript
        for phrase in (
            "verify your identity",
            "verify identity",
            "confirm your identity",
            "confirm identity",
            "pull up your record",
            "look up your record",
            "pull up your account",
            "look up your account",
        )
    ):
        return True
    asks_verification = any(
        phrase in normalized_transcript
        for phrase in (
            "verify",
            "confirm",
            "pull up",
            "look up",
        )
    )
    asks_name = any(
        phrase in normalized_transcript
        for phrase in (
            "your name",
            "full name",
            "first and last name",
        )
    )
    return asks_verification and asks_name


def _asks_to_start_scheduling(normalized_transcript: str) -> bool:
    if _asks_about_appointment_type(normalized_transcript):
        return True
    if _asks_about_provider_preference(normalized_transcript):
        return True
    if "schedule" in normalized_transcript and "provider" in normalized_transcript:
        return True
    return any(
        phrase in normalized_transcript
        for phrase in (
            "would you like to schedule",
            "do you want to schedule",
            "are you trying to schedule",
            "are you calling to schedule",
            "looking to schedule",
            "ready to schedule",
            "ready to book",
            "would you like to book",
            "do you want to book",
            "are you trying to book",
            "looking to book",
            "do you need an appointment",
            "is this for an appointment",
            "is this about an appointment",
            "make an appointment",
            "book an appointment",
            "schedule an appointment",
            "set up an appointment",
            "get you scheduled",
            "get you booked",
            "available appointment times",
            "appointment times",
            "appointment options",
            "look at availability",
            "check availability",
        )
    )


def _name_spelling_answer(scenario: Scenario, normalized_transcript: str) -> str:
    spelling_key = _requested_name_spelling_key(scenario, normalized_transcript)
    first_spelling = scenario.facts.get("first_name_spelling", "").strip()
    last_spelling = scenario.facts.get("last_name_spelling", "").strip()
    if spelling_key == "first_name_spelling":
        return first_spelling
    if spelling_key == "last_name_spelling":
        return last_spelling
    if spelling_key == "name_spelling":
        return " ".join(part for part in (first_spelling, last_spelling) if part)
    return ""


def _requested_name_spelling_key(
    scenario: Scenario,
    normalized_transcript: str,
) -> str:
    if "spell" not in normalized_transcript:
        return ""

    first_name = _caller_first_name(scenario).casefold()
    last_name = _caller_last_name(scenario).casefold()
    has_first_spelling = bool(scenario.facts.get("first_name_spelling", "").strip())
    has_last_spelling = bool(scenario.facts.get("last_name_spelling", "").strip())

    if has_first_spelling and has_last_spelling and (
        "full name" in normalized_transcript
        or "first and last" in normalized_transcript
        or "first name and last name" in normalized_transcript
    ):
        return "name_spelling"
    if has_first_spelling and (
        "first name" in normalized_transcript
        or (first_name and first_name in normalized_transcript)
    ):
        return "first_name_spelling"
    if has_last_spelling and (
        "last name" in normalized_transcript
        or "surname" in normalized_transcript
        or (last_name and last_name in normalized_transcript)
    ):
        return "last_name_spelling"
    if has_first_spelling or has_last_spelling:
        if (
            "name" in normalized_transcript
            or "surname" in normalized_transcript
        ):
            return "name_spelling"
    return ""


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

    transcript_tokens = set(re.findall(r"[a-z]+|\d+", normalized_transcript))
    for key in ("date_of_birth", "patient_date_of_birth"):
        dob = scenario.facts.get(key, "").strip()
        if not dob:
            continue
        dob_tokens = re.findall(r"[a-z]+|\d+", dob.casefold())
        if any(token in transcript_tokens for token in dob_tokens):
            return True
    return False


def build_fact_confirmation_answer(
    scenario: Scenario,
    transcript: str,
    normalized_transcript: str,
) -> str:
    if not _asks_to_confirm_known_facts(scenario, transcript, normalized_transcript):
        return ""

    phone = scenario.facts.get("phone", "").strip()
    phone_digits = _digits_only(phone)
    transcript_phone_digits = _phone_like_digit_groups(transcript)
    wrong_phone_digits = [
        digits
        for digits in transcript_phone_digits
        if phone_digits and _phone_digits_mismatch(phone_digits, digits)
    ]
    if wrong_phone_digits:
        if _mentions_confirmed_name(scenario, normalized_transcript) or _asks_to_confirm_known_date_of_birth(
            scenario,
            transcript,
            normalized_transcript,
        ):
            return (
                "My name and date of birth are correct, but that phone number is not mine. "
                f"My phone number is {phone}."
            )
        return f"That phone number is not mine. My phone number is {phone}."

    if _mentions_wrong_name_for_confirmation(scenario, normalized_transcript):
        return f"No, my name is {_caller_full_name(scenario)}."

    return "Yes, that's correct."


def transcript_is_fact_confirmation_prompt(scenario: Scenario, transcript: str) -> bool:
    normalized_transcript = transcript.casefold()
    return _asks_to_confirm_known_facts(scenario, transcript, normalized_transcript)


def transcript_is_fact_readback_fragment(scenario: Scenario, transcript: str) -> bool:
    if "?" in transcript:
        return False

    normalized_transcript = transcript.casefold()
    if _mentions_confirmed_name(scenario, normalized_transcript):
        return _looks_like_fact_readback(normalized_transcript)
    if _mentions_known_date_of_birth(scenario, normalized_transcript):
        return _looks_like_fact_readback(normalized_transcript)
    if _mentions_phone_readback(scenario, transcript, normalized_transcript):
        return True
    return False


def transcript_is_fact_readback_continuation(transcript: str) -> bool:
    if "?" in transcript:
        return False

    words = re.findall(r"[a-z]+|\d+", transcript.casefold())
    if not words:
        return False
    if len(words) > 8:
        return False
    return all(word.isdigit() or word in NUMBER_WORDS for word in words)


def transcript_completes_fact_readback_confirmation(transcript: str) -> bool:
    normalized_transcript = transcript.casefold().strip()
    if transcript_is_bare_fact_confirmation_question(transcript):
        return True
    return any(
        phrase in normalized_transcript
        for phrase in (
            "is that correct",
            "is all of that correct",
            "is this correct",
            "is that right",
            "is this right",
            "if so",
        )
    )


def transcript_is_bare_fact_confirmation_question(transcript: str) -> bool:
    normalized_transcript = transcript.casefold().strip()
    normalized_transcript = re.sub(r"\s+", " ", normalized_transcript)
    normalized_transcript = normalized_transcript.strip(" .!?")
    return normalized_transcript in {
        "correct",
        "right",
        "is that correct",
        "is all of that correct",
        "is this correct",
        "is that right",
        "is this right",
    }


def _asks_to_confirm_known_facts(
    scenario: Scenario,
    transcript: str,
    normalized_transcript: str,
) -> bool:
    if "?" not in transcript:
        return False
    if _asks_to_confirm_known_date_of_birth(scenario, transcript, normalized_transcript):
        return True
    if not _looks_like_fact_confirmation(normalized_transcript):
        return False
    if _mentions_confirmed_name(scenario, normalized_transcript):
        return True
    if _phone_like_digit_groups(transcript):
        return True
    return False


def _looks_like_fact_confirmation(normalized_transcript: str) -> bool:
    return any(
        phrase in normalized_transcript
        for phrase in (
            "to confirm",
            "confirming",
            "i have",
            "is that correct",
            "is all of that correct",
            "is this correct",
            "is that right",
            "is this right",
            "correct?",
            "right?",
        )
    )


def _looks_like_fact_readback(normalized_transcript: str) -> bool:
    return any(
        phrase in normalized_transcript
        for phrase in (
            "to confirm",
            "confirming",
            "i have",
            "your name as",
            "your date of birth as",
            "your date of birth is",
            "date of birth as",
            "date of birth is",
            "birthdate as",
            "birthdate is",
            "phone number as",
            "phone number is",
            "number as",
            "number is",
        )
    )


def _mentions_confirmed_name(scenario: Scenario, normalized_transcript: str) -> bool:
    full_name = _caller_full_name(scenario).casefold()
    first_name = _caller_first_name(scenario).casefold()
    last_name = _caller_last_name(scenario).casefold()
    return bool(
        full_name and full_name in normalized_transcript
        or (first_name and last_name and first_name in normalized_transcript and last_name in normalized_transcript)
    )


def _mentions_known_date_of_birth(
    scenario: Scenario,
    normalized_transcript: str,
) -> bool:
    transcript_tokens = set(re.findall(r"[a-z]+|\d+", normalized_transcript))
    for key in ("date_of_birth", "patient_date_of_birth"):
        dob = scenario.facts.get(key, "").strip()
        if not dob:
            continue
        dob_tokens = re.findall(r"[a-z]+|\d+", dob.casefold())
        if dob_tokens and any(token in transcript_tokens for token in dob_tokens):
            return True
    return False


def _mentions_phone_readback(
    scenario: Scenario,
    transcript: str,
    normalized_transcript: str,
) -> bool:
    if not any(phrase in normalized_transcript for phrase in ("phone", "number")):
        return False
    if not _looks_like_fact_readback(normalized_transcript):
        return False

    phone = scenario.facts.get("phone", "").strip()
    phone_digits = _digits_only(phone)
    transcript_digits = _digits_only(transcript)
    if phone_digits and transcript_digits and phone_digits.startswith(transcript_digits):
        return True
    if transcript_digits:
        return True

    words = set(re.findall(r"[a-z]+", normalized_transcript))
    return bool(words & NUMBER_WORDS)


def _mentions_wrong_name_for_confirmation(
    scenario: Scenario,
    normalized_transcript: str,
) -> bool:
    if "name" not in normalized_transcript:
        return False
    if _mentions_confirmed_name(scenario, normalized_transcript):
        return False
    if not any(
        phrase in normalized_transcript
        for phrase in (
            "your name as",
            "your name is",
            "name as",
            "name is",
        )
    ):
        return False
    return _looks_like_fact_confirmation(normalized_transcript)


def _digits_only(text: str) -> str:
    return re.sub(r"\D+", "", text)


def _phone_like_digit_groups(text: str) -> list[str]:
    phone_groups: list[str] = []
    for match in re.finditer(r"(?:\+?\d[\d\s().-]{6,}\d)", text):
        digits = _digits_only(match.group(0))
        if len(digits) >= 7:
            phone_groups.append(digits)
    return phone_groups


def _phone_digits_mismatch(expected_digits: str, actual_digits: str) -> bool:
    expected = expected_digits[-10:] if len(expected_digits) >= 10 else expected_digits
    actual = actual_digits[-10:] if len(actual_digits) >= 10 else actual_digits
    return expected != actual


def build_confusion_reply(scenario: Scenario, transcript: str) -> str:
    normalized = transcript.casefold()

    if (
        "birthdate doesn't match" in normalized
        or "date of birth doesn't match" in normalized
        or "birth date doesn't match" in normalized
        or "birthday doesn't match" in normalized
    ):
        dob = scenario.facts.get("date_of_birth", "").strip()
        return (
            f"I don't understand. My date of birth is {format_spoken_date(dob)}."
            if dob
            else "I don't understand."
        )

    if "dental" in normalized:
        return "I don't understand; I thought I called orthopedics."

    new_patient_mismatch = new_patient_appointment_mismatch(scenario, normalized)
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


def _asks_about_date_of_birth(normalized_transcript: str) -> bool:
    return any(
        phrase in normalized_transcript
        for phrase in (
            "date of birth",
            "birth date",
            "birthdate",
            "birthday",
            "dob",
        )
    )


def _asks_about_provider_preference(normalized_transcript: str) -> bool:
    return any(
        phrase in normalized_transcript
        for phrase in (
            "provider preference",
            "preferred provider",
            "provider you'd like",
            "provider you would like",
            "specific provider",
            "particular provider",
            "doctor you'd like",
            "doctor you would like",
            "specific doctor",
            "particular doctor",
            "open to anyone",
            "any provider",
            "whoever is available",
        )
    )
