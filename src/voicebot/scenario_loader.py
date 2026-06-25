"""YAML loading, validation, and Scenario construction."""

from __future__ import annotations

import re
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from voicebot.personas import PersonaNotFoundError, load_persona


SCENARIO_ROOT = Path(__file__).with_name("scenarios")
COMPOSED_SCENARIO_PATIENT_SEPARATOR = "__patient_"
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
PATIENT_FACT_KEYS = {
    "full_name",
    "first_name",
    "last_name",
    "first_name_spelling",
    "last_name_spelling",
    "date_of_birth",
    "phone",
    "insurance",
    "insurance_supplemental",
    "insurance_plan_id_available",
    "pharmacy",
    "preferred_name",
    "legal_name",
    "reason_for_visit",
    "name_variations",
    "temperament",
    "persona_notes",
    "escalation_triggers",
    "de_escalation_triggers",
    "characteristic_phrases",
}


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
    fungible: bool = True
    limits: CallLimits = field(
        default_factory=lambda: CallLimits(
            max_call_seconds=240,
            max_silence_seconds=20,
            max_turns=34,
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


def _add_persona_name_facts(facts: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(facts)
    legal_name = str(enriched.get("legal_name", "")).strip()
    preferred_name = str(enriched.get("preferred_name", "")).strip()
    if legal_name and "full_name" not in enriched:
        enriched["full_name"] = legal_name
    if preferred_name and "first_name" not in enriched:
        enriched["first_name"] = preferred_name
    if legal_name and "last_name" not in enriched:
        parts = legal_name.split()
        if len(parts) > 1:
            enriched["last_name"] = parts[-1]
    return _add_name_spelling_facts(enriched)


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


def _is_patient_fact_key(key: str) -> bool:
    return key in PATIENT_FACT_KEYS or key.startswith("voice_")


def _persona_facts_for_profile(patient_profile: str) -> tuple[dict[str, Any], list[str]]:
    try:
        persona = load_persona(patient_profile)
    except PersonaNotFoundError:
        return {}, []

    facts = _add_persona_name_facts(persona.to_facts())
    return facts, persona.name_variations


def _extract_patient_facts_from_scenario_mapping(data: dict[str, Any]) -> dict[str, Any]:
    raw_facts = data.get("facts", {})
    if not isinstance(raw_facts, dict):
        return {}
    facts = {
        str(key): item
        for key, item in raw_facts.items()
        if _is_patient_fact_key(str(key))
    }
    return _add_name_spelling_facts(facts)


def _scenario_mapping_is_fungible(data: dict[str, Any]) -> bool:
    return _as_bool(data.get("fungible", True))


def _patient_facts_for_profile(
    patient_profile: str,
    root: Path = SCENARIO_ROOT,
) -> tuple[dict[str, Any], list[str]]:
    persona_facts, persona_name_variations = _persona_facts_for_profile(patient_profile)
    if persona_facts:
        return persona_facts, persona_name_variations

    if not root.exists():
        return {}, []
    for path in sorted(root.glob("*.yaml")):
        data = _load_yaml(path)
        if str(data.get("patient_profile", "")) != patient_profile:
            continue
        if not _scenario_mapping_is_fungible(data):
            continue
        facts = _extract_patient_facts_from_scenario_mapping(data)
        if facts:
            name_variations = facts.get("name_variations", [])
            if isinstance(name_variations, list):
                return facts, [str(item) for item in name_variations]
            return facts, []
    return {}, []


def compose_scenario_patient_id(scenario_id: str, patient_profile: str) -> str:
    return f"{scenario_id}{COMPOSED_SCENARIO_PATIENT_SEPARATOR}{patient_profile}"


def split_composed_scenario_patient_id(scenario_id: str) -> tuple[str, str] | None:
    if COMPOSED_SCENARIO_PATIENT_SEPARATOR not in scenario_id:
        return None
    scenario_part, patient_part = scenario_id.rsplit(
        COMPOSED_SCENARIO_PATIENT_SEPARATOR,
        1,
    )
    scenario_part = scenario_part.strip()
    patient_part = patient_part.strip()
    if not scenario_part or not patient_part:
        return None
    return scenario_part, patient_part


def fungible_patient_profiles(root: Path = SCENARIO_ROOT) -> list[str]:
    profiles: dict[str, None] = {}
    persona_root = root.parent / "personas"
    if persona_root.exists():
        for path in sorted(persona_root.glob("*.yaml")):
            data = _load_yaml(path)
            profile_id = str(data.get("id", path.stem))
            facts, _ = _persona_facts_for_profile(profile_id)
            if {"full_name", "date_of_birth", "phone"} <= set(facts):
                profiles[profile_id] = None

    if root.exists():
        for path in sorted(root.glob("*.yaml")):
            data = _load_yaml(path)
            if not _scenario_mapping_is_fungible(data):
                continue
            profile_id = str(data.get("patient_profile", ""))
            facts = _extract_patient_facts_from_scenario_mapping(data)
            if profile_id and {"full_name", "date_of_birth", "phone"} <= set(facts):
                profiles[profile_id] = None
    return list(profiles)


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
        max_turns=34,
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


def _compose_scenario_with_patient_profile(
    scenario: Scenario,
    patient_profile: str,
    *,
    scenario_reference: str,
    root: Path,
) -> Scenario:
    if not scenario.fungible:
        raise ValueError(
            f"Scenario '{scenario_reference}' is non-fungible and cannot be paired "
            f"with patient profile '{patient_profile}'."
        )

    patient_facts, patient_name_variations = _patient_facts_for_profile(
        patient_profile,
        root,
    )
    if not patient_facts:
        raise PersonaNotFoundError(
            f"No reusable patient facts found for profile '{patient_profile}'."
        )

    scenario_facts = {
        key: value
        for key, value in scenario.facts.items()
        if not _is_patient_fact_key(key)
    }
    facts = _add_name_spelling_facts({**patient_facts, **scenario_facts})
    required_facts = _add_name_spelling_required_facts(scenario.required_facts, facts)
    missing_fact_values = sorted(set(required_facts) - set(facts.keys()))
    if missing_fact_values:
        joined = ", ".join(missing_fact_values)
        raise ValueError(
            f"Scenario '{scenario_reference}' paired with patient profile "
            f"'{patient_profile}' is missing required facts: {joined}"
        )

    return Scenario(
        id=compose_scenario_patient_id(scenario.id, patient_profile),
        patient_profile=patient_profile,
        goal=scenario.goal,
        opening_line=scenario.opening_line,
        facts=facts,
        required_facts=required_facts,
        must_test=scenario.must_test,
        avoid=list(scenario.avoid),
        optional_edge_behavior=list(scenario.optional_edge_behavior),
        branch_conditions=list(scenario.optional_edge_behavior),
        success_criteria=scenario.success_criteria,
        stop_conditions=list(scenario.stop_conditions),
        scheduling_rules=list(scenario.scheduling_rules),
        interruption_test=scenario.interruption_test,
        interruption_behavior=dict(scenario.interruption_behavior),
        name_variations=list(patient_name_variations),
        fungible=scenario.fungible,
        limits=scenario.limits,
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
        fungible=_scenario_mapping_is_fungible(data),
        limits=limits,
    )


def load_scenario(scenario_id: str, root: Path = SCENARIO_ROOT) -> Scenario:
    """Load a scenario by file stem or by the scenario's declared id."""

    composed = split_composed_scenario_patient_id(scenario_id)
    if composed is not None:
        base_scenario_id, patient_profile = composed
        path = scenario_path_for_id(base_scenario_id, root)
        scenario = _scenario_from_mapping(_load_yaml(path), path)
        return _compose_scenario_with_patient_profile(
            scenario,
            patient_profile,
            scenario_reference=base_scenario_id,
            root=root,
        )

    path = scenario_path_for_id(scenario_id, root)
    return _scenario_from_mapping(_load_yaml(path), path)


def scenario_path_for_id(scenario_id: str, root: Path = SCENARIO_ROOT) -> Path:
    """Return the YAML path for a scenario file stem or declared scenario id."""

    composed = split_composed_scenario_patient_id(scenario_id)
    if composed is not None:
        return scenario_path_for_id(composed[0], root)

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


def _profile_can_run_scenario(
    scenario_reference: str,
    patient_profile: str,
    root: Path,
) -> bool:
    try:
        load_scenario(
            compose_scenario_patient_id(scenario_reference, patient_profile),
            root,
        )
    except (PersonaNotFoundError, ScenarioNotFoundError, ValueError):
        return False
    return True


def build_shuffled_call_set(
    scenario_ids: list[str] | None = None,
    *,
    seed: int | str | None = None,
    root: Path = SCENARIO_ROOT,
) -> list[str]:
    """Return scenario ids with fungible scenarios paired to shuffled patients.

    Non-fungible scenarios stay as their original ids. Fungible scenarios are
    emitted as composed ids that the loader can resolve at call time.
    """

    selected = list(scenario_ids if scenario_ids is not None else ordered_scenario_stems(root))
    profiles = fungible_patient_profiles(root)
    rng = random.Random(seed)
    rng.shuffle(profiles)

    shuffled: list[str] = []
    used_pairs: set[tuple[str, str]] = set()
    profile_cursor = 0
    for scenario_id in selected:
        path = scenario_path_for_id(scenario_id, root)
        scenario_reference = path.stem
        scenario = _scenario_from_mapping(_load_yaml(path), path)
        if not scenario.fungible or not profiles:
            shuffled.append(scenario_id)
            continue

        chosen_profile = ""
        for offset in range(len(profiles)):
            index = (profile_cursor + offset) % len(profiles)
            candidate = profiles[index]
            pair = (scenario_reference, candidate)
            if pair in used_pairs:
                continue
            if _profile_can_run_scenario(scenario_reference, candidate, root):
                chosen_profile = candidate
                profile_cursor = (index + 1) % len(profiles)
                break

        if not chosen_profile:
            shuffled.append(scenario_id)
            continue

        used_pairs.add((scenario_reference, chosen_profile))
        shuffled.append(compose_scenario_patient_id(scenario_reference, chosen_profile))
    return shuffled
