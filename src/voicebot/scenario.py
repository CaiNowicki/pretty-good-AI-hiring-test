"""Scenario loading and realtime prompt construction."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from voicebot.personas import PersonaNotFoundError, load_persona


SCENARIO_ROOT = Path(__file__).with_name("scenarios")
SCENARIO_RUN_PREFIXES = ("t", "a", "m", "i", "e", "d")
META_BEHAVIOR_ALLOW_PHRASES = (
    "acknowledge this is a test",
    "acknowledge you are a test",
    "admit this is a test",
    "disclose this is a test",
    "explain this is a test",
    "mention this is a test",
    "reveal this is a test",
    "say this is a test",
    "state this is a test",
    "tell the agent this is a test",
    "test harness",
    "meta behavior",
)
DEFAULT_EMERGENCY_STOP_PHRASES = (
    "emergency stop",
    "stop the test",
    "stop this test",
    "end the test call",
    "abort the call",
    "hang up now",
)


@dataclass(frozen=True)
class CallLimits:
    max_call_seconds: int
    max_silence_seconds: int
    max_turns: int
    emergency_stop_phrases: list[str] = field(
        default_factory=lambda: list(DEFAULT_EMERGENCY_STOP_PHRASES)
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Scenario:
    id: str
    patient_profile: str
    goal: str
    opening_line: str
    facts: dict[str, Any]
    required_facts: list[str]
    must_test: str
    avoid: list[str]
    optional_edge_behavior: list[str]
    branch_conditions: list[str]
    success_criteria: str
    stop_conditions: list[str]
    interruption_test: bool = False
    interruption_behavior: dict[str, str] = field(default_factory=dict)
    name_variations: list[str] = field(default_factory=list)
    limits: CallLimits = field(
        default_factory=lambda: CallLimits(
            max_call_seconds=240,
            max_silence_seconds=20,
            max_turns=22,
        )
    )


class ScenarioNotFoundError(FileNotFoundError):
    """Raised when a requested scenario id has no matching YAML file."""


def _clean_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by scenario files.

    This fallback intentionally supports only top-level scalars, one-level
    mappings, one-level lists, and folded multiline strings.
    """

    result: dict[str, Any] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            index += 1
            continue
        if raw_line.startswith((" ", "\t")) or ":" not in raw_line:
            raise ValueError(f"Unsupported scenario YAML line: {raw_line}")

        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        index += 1

        if value == ">":
            folded: list[str] = []
            while index < len(lines):
                child = lines[index]
                if child and not child.startswith((" ", "\t")):
                    break
                if child.strip():
                    folded.append(child.strip())
                index += 1
            result[key] = " ".join(folded)
            continue

        if value:
            result[key] = _clean_scalar(value)
            continue

        children: list[str] = []
        while index < len(lines):
            child = lines[index]
            if child and not child.startswith((" ", "\t")):
                break
            if child.strip():
                children.append(child.strip())
            index += 1

        if all(child.startswith("- ") for child in children):
            result[key] = [_clean_scalar(child[2:]) for child in children]
            continue

        mapping: dict[str, str] = {}
        for child in children:
            if ":" not in child:
                raise ValueError(f"Unsupported scenario YAML mapping line: {child}")
            child_key, child_value = child.split(":", 1)
            mapping[child_key.strip()] = _clean_scalar(child_value)
        result[key] = mapping

    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return _parse_simple_yaml(path.read_text(encoding="utf-8"))

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Scenario file {path} did not contain a mapping.")
    return data


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _as_string_list(value: Any, path: Path, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"Scenario file {path} has non-list {field}.")
    return [str(item) for item in value]


def _as_string_mapping(value: Any, path: Path, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"Scenario file {path} has non-mapping {field}.")
    return {str(key): str(item) for key, item in value.items()}


def _as_fact_mapping(value: Any, path: Path, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Scenario file {path} has non-mapping {field}.")

    facts: dict[str, Any] = {}
    for key, item in value.items():
        fact_key = str(key)
        if isinstance(item, list):
            facts[fact_key] = [str(child) for child in item]
        else:
            facts[fact_key] = str(item)
    return facts


def _persona_facts_for_profile(patient_profile: str) -> tuple[dict[str, Any], list[str]]:
    try:
        persona = load_persona(patient_profile)
    except PersonaNotFoundError:
        return {}, []

    facts = persona.to_facts()
    return facts, persona.name_variations


def _as_positive_int(value: Any, path: Path, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Scenario file {path} has non-integer {field}.") from exc
    if parsed <= 0:
        raise ValueError(f"Scenario file {path} has non-positive {field}.")
    return parsed


def _call_duration_from_stop_conditions(stop_conditions: list[str]) -> int | None:
    for condition in stop_conditions:
        match = re.search(r"call exceeds\s+(\d+)\s+minute", condition, re.IGNORECASE)
        if match:
            return int(match.group(1)) * 60
    return None


def _default_limits_for_scenario(
    scenario_id: str,
    patient_profile: str,
    stop_conditions: list[str],
    interruption_test: bool,
) -> CallLimits:
    max_call_seconds = _call_duration_from_stop_conditions(stop_conditions) or 240
    normalized_id = scenario_id.casefold()

    if patient_profile == "distressed_adult_caller" or "medical-emergency" in normalized_id:
        return CallLimits(
            max_call_seconds=max_call_seconds,
            max_silence_seconds=10,
            max_turns=12,
        )
    if interruption_test or patient_profile == "impatient_adult_caller":
        return CallLimits(
            max_call_seconds=max_call_seconds,
            max_silence_seconds=8,
            max_turns=34,
        )
    if "hard-of-hearing" in normalized_id:
        return CallLimits(
            max_call_seconds=max_call_seconds,
            max_silence_seconds=24,
            max_turns=36,
        )
    if "background-interruptions" in normalized_id:
        return CallLimits(
            max_call_seconds=max_call_seconds,
            max_silence_seconds=18,
            max_turns=34,
        )
    if normalized_id.startswith("i-"):
        return CallLimits(
            max_call_seconds=max_call_seconds,
            max_silence_seconds=18,
            max_turns=16,
        )
    return CallLimits(
        max_call_seconds=max_call_seconds,
        max_silence_seconds=20,
        max_turns=22,
    )


def _call_limits_from_mapping(
    data: dict[str, Any],
    path: Path,
    stop_conditions: list[str],
    interruption_test: bool,
) -> CallLimits:
    defaults = _default_limits_for_scenario(
        str(data["id"]),
        str(data["patient_profile"]),
        stop_conditions,
        interruption_test,
    )
    raw_limits = data.get("limits", {})
    if not raw_limits:
        return defaults
    if not isinstance(raw_limits, dict):
        raise ValueError(f"Scenario file {path} has non-mapping limits.")

    emergency_stop_phrases = raw_limits.get(
        "emergency_stop_phrases",
        defaults.emergency_stop_phrases,
    )
    if not isinstance(emergency_stop_phrases, list):
        raise ValueError(f"Scenario file {path} has non-list limits.emergency_stop_phrases.")

    return CallLimits(
        max_call_seconds=_as_positive_int(
            raw_limits.get("max_call_seconds", defaults.max_call_seconds),
            path,
            "limits.max_call_seconds",
        ),
        max_silence_seconds=_as_positive_int(
            raw_limits.get("max_silence_seconds", defaults.max_silence_seconds),
            path,
            "limits.max_silence_seconds",
        ),
        max_turns=_as_positive_int(
            raw_limits.get("max_turns", defaults.max_turns),
            path,
            "limits.max_turns",
        ),
        emergency_stop_phrases=[str(phrase) for phrase in emergency_stop_phrases],
    )


def _scenario_from_mapping(data: dict[str, Any], path: Path) -> Scenario:
    required = {
        "id",
        "patient_profile",
        "goal",
        "opening_line",
        "facts",
        "required_facts",
        "must_test",
        "avoid",
        "optional_edge_behavior",
        "success_criteria",
        "stop_conditions",
    }
    missing = sorted(required - data.keys())
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Scenario file {path} is missing required fields: {joined}")

    scenario_facts = _as_fact_mapping(data["facts"], path, "facts")
    persona_facts, persona_name_variations = _persona_facts_for_profile(
        str(data["patient_profile"])
    )
    facts = {**persona_facts, **scenario_facts}

    required_facts = _as_string_list(data["required_facts"], path, "required_facts")
    missing_fact_values = sorted(set(required_facts) - set(facts.keys()))
    if missing_fact_values:
        joined = ", ".join(missing_fact_values)
        raise ValueError(
            f"Scenario file {path} lists required facts without values: {joined}"
        )

    optional_edge_behavior = _as_string_list(
        data["optional_edge_behavior"], path, "optional_edge_behavior"
    )
    interruption_behavior = _as_string_mapping(
        data.get("interruption_behavior", {}), path, "interruption_behavior"
    )
    interruption_test = _as_bool(data.get("interruption_test", False))
    if interruption_test and not interruption_behavior:
        raise ValueError(
            f"Scenario file {path} marks interruption_test without interruption_behavior."
        )
    if not interruption_test and interruption_behavior:
        raise ValueError(
            f"Scenario file {path} defines interruption_behavior without interruption_test."
        )
    stop_conditions = _as_string_list(data["stop_conditions"], path, "stop_conditions")
    limits = _call_limits_from_mapping(data, path, stop_conditions, interruption_test)

    return Scenario(
        id=str(data["id"]),
        patient_profile=str(data["patient_profile"]),
        goal=str(data["goal"]),
        opening_line=str(data["opening_line"]),
        facts=facts,
        required_facts=required_facts,
        must_test=str(data["must_test"]),
        avoid=_as_string_list(data["avoid"], path, "avoid"),
        optional_edge_behavior=optional_edge_behavior,
        branch_conditions=optional_edge_behavior,
        success_criteria=str(data["success_criteria"]),
        stop_conditions=stop_conditions,
        interruption_test=interruption_test,
        interruption_behavior=interruption_behavior,
        name_variations=_as_string_list(
            data.get("name_variations", persona_name_variations),
            path,
            "name_variations",
        ),
        limits=limits,
    )


def load_scenario(scenario_id: str, root: Path = SCENARIO_ROOT) -> Scenario:
    """Load a scenario by file stem or by the scenario's declared id."""

    direct_path = root / f"{scenario_id}.yaml"
    if direct_path.exists():
        return _scenario_from_mapping(_load_yaml(direct_path), direct_path)

    if root.exists():
        for path in sorted(root.glob("*.yaml")):
            scenario = _scenario_from_mapping(_load_yaml(path), path)
            if scenario.id == scenario_id:
                return scenario

    raise ScenarioNotFoundError(f"No scenario found for id '{scenario_id}' in {root}.")


def ordered_scenario_stems(root: Path = SCENARIO_ROOT) -> list[str]:
    """Return scenario file stems in the intended batch execution order."""

    def sort_key(path: Path) -> tuple[int, str]:
        prefix = path.stem[:1].casefold()
        try:
            prefix_index = SCENARIO_RUN_PREFIXES.index(prefix)
        except ValueError:
            prefix_index = len(SCENARIO_RUN_PREFIXES)
        return (prefix_index, path.stem)

    if not root.exists():
        return []
    return [path.stem for path in sorted(root.glob("*.yaml"), key=sort_key)]


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
        return ", ".join(str(item) for item in value)
    return str(value)


def _format_fact_lines(facts: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in facts.items():
        lines.append(f"- {key}: {_format_fact_value(value)}")
    return "\n".join(lines)


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
    return "\n".join(f"- {item}" for item in items)


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


def build_patient_system_prompt(scenario: Scenario) -> str:
    """Build the realtime model instructions from scenario facts."""

    facts = _format_fact_lines(scenario.facts)
    required_facts = ", ".join(scenario.required_facts)
    avoid = "\n".join(f"- {item}" for item in scenario.avoid)
    edge_behavior = "\n".join(f"- {item}" for item in scenario.optional_edge_behavior)
    stop_conditions = "\n".join(f"- {item}" for item in scenario.stop_conditions)
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
    strategy_section = """
Conversation strategy:
- Answer direct questions with the relevant scenario fact and stop there.
- Ask one brief follow-up when the agent's offer is incomplete or ambiguous.
- Correct misunderstandings plainly, then return to the scheduling or information goal.
- If the agent drifts, politely steer back to the goal without taking over the agent's role.
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

Required fact keys that must be preserved exactly when asked: {required_facts}

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
{interruption_guidance}
{meta_guidance}
Say the opening line once only. If you already introduced yourself, do not repeat the
opening line later; answer the current question or steer back to the goal instead.
You are the patient, not the clinic staff or scheduling agent. Never say you are checking,
scheduling, booking, creating, adjusting, or rescheduling appointments yourself. Ask the
agent to do those things for you.
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
