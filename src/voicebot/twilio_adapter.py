"""Twilio outbound call adapter."""

from __future__ import annotations

from dataclasses import asdict
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


def create_outbound_call(settings: Settings, to_number: str, scenario_id: str) -> dict[str, Any]:
    missing = settings.missing_twilio_call_values()
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required Twilio call configuration: {joined}")

    plan = build_call_plan(settings, to_number, scenario_id)

    try:
        from twilio.rest import Client
    except ImportError as exc:
        raise RuntimeError("Install project dependencies before placing calls.") from exc

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    call = client.calls.create(
        to=plan["to"],
        from_=plan["from"],
        url=plan["url"],
        record=plan["record"],
    )
    return {
        "sid": call.sid,
        "status": call.status,
        "plan": plan,
        "settings": {
            key: value
            for key, value in asdict(settings).items()
            if "token" not in key and "key" not in key
        },
    }

