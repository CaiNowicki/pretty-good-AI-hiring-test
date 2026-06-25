"""YAML loading, validation, and Scenario construction."""

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
    scheduling_rules: list[str] = field(default_factory=list)
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


def _spelling_for_name(name: str) -> str:
    chunks: list[str] = []
    letters: list[str] = []

    def flush_letters() -> None:
        if letters:
            chunks.append("-".join(letters))
            letters.clear()

    for character in name.strip():
        if character.isalpha():
            letters.append(character.upper())
            continue

        flush_letters()
        if character == "-":
            chunks.append("hyphen")
        elif character == "'":
            chunks.append("apostrophe")
        elif character.isspace():
            chunks.append("space")
        else:
            chunks.append(character)

    flush_letters()
    return " ".join(chunks)


def _add_name_spelling_facts(facts: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(facts)
    for name_key in ("first_name", "last_name"):
        spelling_key = f"{name_key}_spelling"
        name = str(enriched.get(name_key, "")).strip()
        if name and not str(enriched.get(spelling_key, "")).strip():
            enriched[spelling_key] = _spelling_for_name(name)
    return enriched


def _add_name_spelling_required_facts(
    required_facts: list[str],
    facts: dict[str, Any],
) -> list[str]:
    enriched = list(required_facts)
    for name_key in ("first_name", "last_name"):
        spelling_key = f"{name_key}_spelling"
        if name_key in required_facts and spelling_key in facts and spelling_key not in enriched:
            enriched.append(spelling_key)
    return enriched


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
    facts = _add_name_spelling_facts({**persona_facts, **scenario_facts})

    required_facts = _as_string_list(data["required_facts"], path, "required_facts")
    required_facts = _add_name_spelling_required_facts(required_facts, facts)
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
        scheduling_rules=_as_string_list(
            data.get("scheduling_rules", []), path, "scheduling_rules"
        ),
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

    path = scenario_path_for_id(scenario_id, root)
    return _scenario_from_mapping(_load_yaml(path), path)


def scenario_path_for_id(scenario_id: str, root: Path = SCENARIO_ROOT) -> Path:
    """Return the YAML path for a scenario file stem or declared scenario id."""

    direct_path = root / f"{scenario_id}.yaml"
    if direct_path.exists():
        return direct_path

    if root.exists():
        for path in sorted(root.glob("*.yaml")):
            scenario = _scenario_from_mapping(_load_yaml(path), path)
            if scenario.id == scenario_id:
                return path

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
