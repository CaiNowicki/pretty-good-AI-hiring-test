"""System prompt and realtime bootstrap builders from a Scenario."""

from __future__ import annotations

from typing import Any

from voicebot.date_formatting import format_spoken_date, format_spoken_dates_in_text
from voicebot.scenario_loader import META_BEHAVIOR_ALLOW_PHRASES, Scenario


def scenario_allows_meta_behavior(scenario: Scenario) -> bool:
    """Return whether existing scenario behavior text explicitly permits meta talk."""

    searchable_parts = [
        scenario.goal,
        scenario.must_test,
        scenario.success_criteria,
        *scenario.optional_edge_behavior,
    ]
    searchable = " ".join(searchable_parts).casefold()
    return any(phrase in searchable for phrase in META_BEHAVIOR_ALLOW_PHRASES)


def _format_fact_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(format_spoken_dates_in_text(str(item)) for item in value)
    if isinstance(value, str):
        return format_spoken_dates_in_text(format_spoken_date(value))
    return str(value)


def _format_fact_lines(facts: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in facts.items():
        lines.append(f"- {key}: {_format_fact_value(value)}")
    return "\n".join(lines)


def _prompt_facts_for_scenario(scenario: Scenario) -> dict[str, Any]:
    if not _scenario_is_information_gathering(scenario):
        return scenario.facts
    return {
        key: value
        for key, value in scenario.facts.items()
        if key not in {"date_of_birth", "patient_date_of_birth", "phone"}
    }


def _build_name_lookup_guidance(scenario: Scenario) -> str:
    if not scenario.name_variations:
        return ""

    lookup_attempts = [*scenario.name_variations]
    phone = scenario.facts.get("phone", "")
    dob = scenario.facts.get("date_of_birth", "")
    if phone:
        lookup_attempts.append(f"Phone number {_format_fact_value(phone)}")
    if dob:
        lookup_attempts.append(f"Date of birth {_format_fact_value(dob)}")

    ordered_attempts = "\n".join(
        f"{index}. {attempt}" for index, attempt in enumerate(lookup_attempts, start=1)
    )
    return f"""
Name lookup guidance:
Offer lookup values one at a time in this exact order, moving to the next only
after the agent confirms the current attempt did not find a match:
{ordered_attempts}
Do not volunteer the full lookup list at once. If a matching record is found,
verify date of birth before accepting or confirming any appointment details.
"""


def _format_guidance_list(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return "\n".join(f"- {format_spoken_dates_in_text(str(item))}" for item in items)


def _build_persona_behavior_guidance(scenario: Scenario) -> str:
    escalation_triggers = _format_guidance_list(
        scenario.facts.get("escalation_triggers", [])
    )
    de_escalation_triggers = _format_guidance_list(
        scenario.facts.get("de_escalation_triggers", [])
    )
    characteristic_phrases = _format_guidance_list(
        scenario.facts.get("characteristic_phrases", [])
    )
    if not any((escalation_triggers, de_escalation_triggers, characteristic_phrases)):
        return ""

    sections: list[str] = ["Persona behavior guidance:"]
    if escalation_triggers:
        sections.append(f"Escalation triggers:\n{escalation_triggers}")
    if de_escalation_triggers:
        sections.append(f"De-escalation triggers:\n{de_escalation_triggers}")
    if characteristic_phrases:
        sections.append(
            "Characteristic phrases you may use naturally when they fit, not as a "
            f"scripted checklist:\n{characteristic_phrases}"
        )
    return "\n".join(sections) + "\n"


def _scenario_has_scheduling_goal(scenario: Scenario) -> bool:
    searchable_parts = [
        scenario.goal,
        scenario.must_test,
        scenario.success_criteria,
        *scenario.optional_edge_behavior,
        *scenario.stop_conditions,
    ]
    searchable = " ".join(searchable_parts).casefold()
    return any(
        phrase in searchable
        for phrase in (
            "appointment",
            "availability",
            "book",
            "booking",
            "cancel",
            "reschedule",
            "schedule",
            "slot",
        )
    )


def _scenario_is_information_gathering(scenario: Scenario) -> bool:
    return scenario.id.casefold().startswith("i-")


def _build_information_request_guidance(scenario: Scenario) -> str:
    if not _scenario_is_information_gathering(scenario):
        return ""
    return """
Information request boundary:
- You are asking for general office information before deciding whether to book.
- If the agent asks for date of birth, phone number, full identity verification,
  or patient-record lookup before answering the general question, politely push
  back instead of providing it.
- If the agent tries to move into scheduling, appointment type, or booking
  before the general question is answered, politely say
  you are not ready to schedule yet and return to the information question.
- Do not choose a provider, appointment type, appointment time, or transfer path
  for booking during an informational scenario. Once the information question is
  answered, close politely or ask one final information follow-up.
- Use natural wording such as: "I'm just asking a general question right now,
  not trying to book yet. Do you need my personal information to answer that?"
- Provide insurance plan type only when the information question itself requires
  it, such as asking whether a specific plan is accepted.
"""


def _build_scheduling_guidance(scenario: Scenario) -> str:
    if not scenario.scheduling_rules and not _scenario_has_scheduling_goal(scenario):
        return ""

    scenario_rules = ""
    if scenario.scheduling_rules:
        rules = "\n".join(
            f"- {format_spoken_dates_in_text(str(rule))}"
            for rule in scenario.scheduling_rules
        )
        scenario_rules = f"""
Scenario date-selection rules:
{rules}
"""

    return f"""
Scheduling date-selection guidance:
- Stay at the scenario's intended level of date specificity until the agent
  gives a more specific appointment option.
- Before the agent says an exact calendar date, do not invent or say exact
  calendar dates such as "Tuesday June 3rd." Use patient-side relative or broad
  wording instead, such as "this Tuesday," "tomorrow," "sometime early next
  week," "Thursday or Friday morning," or "the earliest weekday morning."
- Once the agent introduces a specific date or time, you may repeat those exact
  details to accept, decline, correct, or confirm them.
- Let the scenario rules decide whether you are broad, narrow, urgent,
  flexible, confused, or changing your mind. Vary the phrasing naturally rather
  than following a fixed wording pattern.
- This guidance is only about appointment dates and times. Provide accurate
  identity facts, such as date of birth, when the agent asks. Say dates in
  natural spoken month/day/year form.
{scenario_rules}"""


def build_scheduling_turn_guidance(scenario: Scenario | None) -> str:
    if scenario is None:
        return ""
    if not scenario.scheduling_rules and not _scenario_has_scheduling_goal(scenario):
        return ""
    return (
        "Scheduling date wording: follow the scenario date-selection rules, stay "
        "general until the agent gives exact calendar details, do not invent exact "
        "month/day dates, and vary natural relative wording."
    )


def build_patient_system_prompt(scenario: Scenario) -> str:
    """Build the realtime model instructions from scenario facts."""

    facts = _format_fact_lines(_prompt_facts_for_scenario(scenario))
    required_facts = ", ".join(scenario.required_facts)
    avoid = _format_guidance_list(scenario.avoid)
    edge_behavior = _format_guidance_list(scenario.optional_edge_behavior)
    stop_conditions = _format_guidance_list(scenario.stop_conditions)
    patient_name = scenario.facts.get(
        "full_name",
        scenario.facts.get(
            "legal_name",
            scenario.facts.get("name", scenario.patient_profile.replace("_", " ").title()),
        ),
    )
    edge_section = ""
    if edge_behavior:
        edge_section = f"""
Optional edge behavior:
{edge_behavior}
"""
    name_lookup_guidance = _build_name_lookup_guidance(scenario)
    persona_behavior_guidance = _build_persona_behavior_guidance(scenario)
    information_request_guidance = _build_information_request_guidance(scenario)
    scheduling_guidance = _build_scheduling_guidance(scenario)
    strategy_section = """
Conversation strategy:
- Answer direct questions with the relevant scenario fact and stop there.
- Ask one brief follow-up when the agent's offer is incomplete or ambiguous.
- Correct misunderstandings plainly, then return to the scheduling or information goal.
- If the agent drifts, politely steer back to the goal without taking over the agent's role.
"""
    role_boundary_section = """
Patient role boundary:
- You are the patient, not clinic staff or the scheduling agent.
- Do not narrate clinic-side work. Never say you can check availability,
  look up the schedule, hold a slot, book, create, adjust, move, cancel,
  confirm, or reschedule appointments yourself.
- Do not say phrases like "let me check", "I can check that", "I can schedule
  you", "I'll book that", "I'll put you down", "I created the appointment",
  "I've changed that", "I'll adjust the time", "you're all set", or "I can
  help you schedule".
- Do use patient language: say what you want, accept or decline offered times,
  and ask the agent to check, book, change, cancel, or confirm appointment
  details for you.
- Patient-side phrases are okay, such as "Could you check that for me?",
  "That works for me if you can book it", "Can you move it to that time?",
  "Could you cancel that appointment?", and "Can you confirm the details?"
"""
    interruption_guidance = (
        _build_interruption_guidance(scenario)
        if scenario.interruption_test
        else (
            "Do not interrupt the agent. If the agent starts speaking while you are speaking, "
            "stop and let the agent finish."
        )
    )
    meta_guidance = (
        "This scenario explicitly calls for meta behavior. Follow only those meta instructions, "
        "keep them brief, and then return to the patient task."
        if scenario_allows_meta_behavior(scenario)
        else (
            "Do not reveal that this is a test, test harness, evaluation, simulation, bot, "
            "assistant, or automated caller. If asked, stay in character as the patient and "
            "redirect to the reason for the call. Do not call it a demo."
        )
    )

    return f"""You are playing the role of {patient_name} in a phone call with a medical scheduling agent.
Patient persona id: {scenario.patient_profile}
Goal: {scenario.goal}

Use these scenario facts to answer the agent's questions:
{facts}

Required fact keys that must be preserved accurately when asked: {required_facts}
For date-of-birth values, preserve the date but say it naturally, such as
"September 27, 1963" instead of "1963-09-27."

Answer with the provided facts only when asked. Do not volunteer everything at once.
Respond to the agent's most recent question only. Do not add unrelated facts,
preferences, or comments just because they are in the scenario. Only mention
referral status, provider preference, insurance, time preference, or appointment
type when the agent asks about it or when you must correct a misunderstanding.
If the agent repeats an appointment-type question, calmly restate the same answer
instead of switching categories.
Use the goal and optional edge behavior as guidance, not as a fixed dialogue script.
Speak in short, natural sentences. Do not use lists or bullet points in spoken replies.
When you need to ask follow-up questions, ask one question at a time and wait
for a complete answer before asking another.
Wait for the agent to finish speaking before responding.
Stay polite and conversational, like a real patient on a phone call.
{strategy_section}
{role_boundary_section}
{information_request_guidance}
{scheduling_guidance}
{interruption_guidance}
{meta_guidance}
Say the opening line once only. If you already introduced yourself, do not repeat the
opening line later; answer the current question or steer back to the goal instead.
{edge_section}
{name_lookup_guidance}
{persona_behavior_guidance}
What this scenario is testing:
{scenario.must_test}

Avoid:
{avoid}

Success criteria:
{scenario.success_criteria}

Stop conditions:
{stop_conditions}

End the call politely once the goal is complete or a stop condition is met.
The first patient utterance for this scenario is: {scenario.opening_line}"""


def build_realtime_bootstrap(scenario: Scenario) -> dict[str, Any]:
    """Return the scenario payload the realtime bridge needs at call start."""

    system_prompt = build_patient_system_prompt(scenario)
    return {
        "scenario_id": scenario.id,
        "patient_profile": scenario.patient_profile,
        "interruption_test": scenario.interruption_test,
        "interruption_behavior": scenario.interruption_behavior,
        "limits": scenario.limits.to_dict(),
        "system_prompt": system_prompt,
        "initial_patient_utterance": scenario.opening_line,
    }


def _build_interruption_guidance(scenario: Scenario) -> str:
    behavior = scenario.interruption_behavior
    trigger = behavior.get("trigger", "only when the scenario explicitly calls for it")
    max_interruptions = behavior.get("max_interruptions", "1")
    line = behavior.get("patient_line", "a brief clarification")
    recovery_rule = behavior.get("recovery_rule", "then let the agent recover")
    measurement_focus = behavior.get(
        "measurement_focus",
        "agent recovery from deliberate barge-in, separate from normal turn-taking",
    )
    return (
        "This is an interruption-handling scenario with explicit barge-in data. "
        f"Interrupt no more than {max_interruptions} time(s), triggered by: {trigger}. "
        f"Use this interruption content: {line}. "
        f"After the interruption: {recovery_rule}. "
        f"Measurement focus: {measurement_focus}."
    )
