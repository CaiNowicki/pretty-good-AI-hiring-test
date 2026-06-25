"""Pure Twilio call-plan and media wire-message constructors."""

from __future__ import annotations

from typing import Any

from voicebot.config import Settings
from voicebot.safety import validate_destination


def build_voice_webhook_url(settings: Settings, scenario_id: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/twilio/voice?scenario_id={scenario_id}"


def build_call_plan(settings: Settings, to_number: str, scenario_id: str) -> dict[str, Any]:
    destination = validate_destination(to_number)
    return {
        "to": destination,
        "from": settings.twilio_from_number,
        "url": build_voice_webhook_url(settings, scenario_id),
        "record": True,
        "scenario_id": scenario_id,
        "allowed_destination": settings.allowed_destination,
    }


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
