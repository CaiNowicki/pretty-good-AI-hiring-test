"""Scenario loading and realtime prompt construction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCENARIO_ROOT = Path(__file__).with_name("scenarios")


@dataclass(frozen=True)
class Scenario:
    id: str
    patient_profile: str
    goal: str
    opening_line: str
    facts: dict[str, str]
    must_test: str
    avoid: list[str]
    branch_conditions: list[str]
    success_criteria: str
    stop_conditions: list[str]


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


def _scenario_from_mapping(data: dict[str, Any], path: Path) -> Scenario:
    required = {
        "id",
        "patient_profile",
        "goal",
        "opening_line",
        "facts",
        "must_test",
        "avoid",
        "success_criteria",
        "stop_conditions",
    }
    missing = sorted(required - data.keys())
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Scenario file {path} is missing required fields: {joined}")

    facts = data["facts"]
    if not isinstance(facts, dict):
        raise ValueError(f"Scenario file {path} has non-mapping facts.")

    return Scenario(
        id=str(data["id"]),
        patient_profile=str(data["patient_profile"]),
        goal=str(data["goal"]),
        opening_line=str(data["opening_line"]),
        facts={str(key): str(value) for key, value in facts.items()},
        must_test=str(data["must_test"]),
        avoid=[str(item) for item in data["avoid"]],
        branch_conditions=[str(item) for item in data.get("branch_conditions", [])],
        success_criteria=str(data["success_criteria"]),
        stop_conditions=[str(item) for item in data["stop_conditions"]],
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


def build_patient_system_prompt(scenario: Scenario) -> str:
    """Build the realtime model instructions from scenario facts."""

    facts = "\n".join(f"- {key}: {value}" for key, value in scenario.facts.items())
    avoid = "\n".join(f"- {item}" for item in scenario.avoid)
    branch_conditions = "\n".join(f"- {item}" for item in scenario.branch_conditions)
    stop_conditions = "\n".join(f"- {item}" for item in scenario.stop_conditions)
    patient_name = scenario.facts.get("name", scenario.patient_profile.replace("_", " ").title())
    branch_section = ""
    if branch_conditions:
        branch_section = f"""
Conditional behavior:
{branch_conditions}
"""

    return f"""You are playing the role of {patient_name} in a phone call with a medical scheduling agent.
Patient persona id: {scenario.patient_profile}
Goal: {scenario.goal}

Use these scenario facts to answer the agent's questions:
{facts}

Answer with the provided facts only when asked. Do not volunteer everything at once.
Use the goal and conditional behavior as guidance, not as a fixed dialogue script.
Speak in short, natural sentences. Do not use lists or bullet points in spoken replies.
Wait for the agent to finish speaking before responding.
Stay polite and conversational, like a real patient on a phone call.
You are the patient, not the clinic staff or scheduling agent. Never say you are checking,
scheduling, booking, creating, adjusting, or rescheduling appointments yourself. Ask the
agent to do those things for you.
{branch_section}
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
        "system_prompt": system_prompt,
        "initial_patient_utterance": scenario.opening_line,
    }
