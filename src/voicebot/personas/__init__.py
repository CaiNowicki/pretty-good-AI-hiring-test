"""Patient persona loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PERSONA_ROOT = Path(__file__).parent


@dataclass(frozen=True)
class Persona:
    id: str
    preferred_name: str = ""
    legal_name: str = ""
    date_of_birth: str = ""
    phone: str = ""
    insurance: str = ""
    pharmacy: str = ""
    reason_for_visit: str = ""
    temperament: str = ""
    name_variations: list[str] = field(default_factory=list)
    escalation_triggers: list[str] = field(default_factory=list)
    de_escalation_triggers: list[str] = field(default_factory=list)
    characteristic_phrases: list[str] = field(default_factory=list)
    notes: str = ""
    voice_profile: dict[str, str] = field(default_factory=dict)

    def to_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        for key in (
            "preferred_name",
            "legal_name",
            "date_of_birth",
            "phone",
            "insurance",
            "pharmacy",
            "reason_for_visit",
            "temperament",
        ):
            value = getattr(self, key)
            if value:
                facts[key] = value
        if self.name_variations:
            facts["name_variations"] = list(self.name_variations)
        if self.escalation_triggers:
            facts["escalation_triggers"] = list(self.escalation_triggers)
        if self.de_escalation_triggers:
            facts["de_escalation_triggers"] = list(self.de_escalation_triggers)
        if self.characteristic_phrases:
            facts["characteristic_phrases"] = list(self.characteristic_phrases)
        if self.notes:
            facts["persona_notes"] = self.notes
        for key, value in self.voice_profile.items():
            facts[f"voice_{key}"] = value
        return facts


class PersonaNotFoundError(FileNotFoundError):
    """Raised when a requested persona id has no matching YAML file."""


def _clean_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            index += 1
            continue
        if raw_line.startswith((" ", "\t")) or ":" not in raw_line:
            raise ValueError(f"Unsupported persona YAML line: {raw_line}")

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
                raise ValueError(f"Unsupported persona YAML mapping line: {child}")
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
        raise ValueError(f"Persona file {path} did not contain a mapping.")
    return data


def _as_string_list(value: Any, path: Path, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Persona file {path} has non-list {field_name}.")
    return [str(item) for item in value]


def _as_string_mapping(value: Any, path: Path, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Persona file {path} has non-mapping {field_name}.")
    return {str(key): str(item) for key, item in value.items()}


def _persona_from_mapping(data: dict[str, Any], path: Path) -> Persona:
    if "id" not in data:
        raise ValueError(f"Persona file {path} is missing required field: id")

    return Persona(
        id=str(data["id"]),
        preferred_name=str(data.get("preferred_name", "")),
        legal_name=str(data.get("legal_name", "")),
        date_of_birth=str(data.get("date_of_birth", "")),
        phone=str(data.get("phone", "")),
        insurance=str(data.get("insurance", "")),
        pharmacy=str(data.get("pharmacy", "")),
        reason_for_visit=str(data.get("reason_for_visit", "")),
        temperament=str(data.get("temperament", "")),
        name_variations=_as_string_list(
            data.get("name_variations", []), path, "name_variations"
        ),
        escalation_triggers=_as_string_list(
            data.get("escalation_triggers", []), path, "escalation_triggers"
        ),
        de_escalation_triggers=_as_string_list(
            data.get("de_escalation_triggers", []), path, "de_escalation_triggers"
        ),
        characteristic_phrases=_as_string_list(
            data.get("characteristic_phrases", []), path, "characteristic_phrases"
        ),
        notes=str(data.get("notes", "")),
        voice_profile=_as_string_mapping(
            data.get("voice_profile", {}), path, "voice_profile"
        ),
    )


def load_persona(persona_id: str, root: Path = PERSONA_ROOT) -> Persona:
    """Load a persona by file stem or by declared id."""

    direct_path = root / f"{persona_id}.yaml"
    if direct_path.exists():
        return _persona_from_mapping(_load_yaml(direct_path), direct_path)

    if root.exists():
        for path in sorted(root.glob("*.yaml")):
            persona = _persona_from_mapping(_load_yaml(path), path)
            if persona.id == persona_id:
                return persona

    raise PersonaNotFoundError(f"No persona found for id '{persona_id}' in {root}.")
