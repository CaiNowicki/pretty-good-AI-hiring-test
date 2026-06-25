"""Side-effectful Twilio call creation."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from voicebot.config import Settings
from voicebot.twilio_builders import build_call_plan


def create_outbound_call(
    settings: Settings,
    to_number: str,
    scenario_id: str,
    *,
    call_id: str = "",
    call_type: str = "",
    call_dir_name: str = "",
) -> dict[str, Any]:
    missing = settings.missing_twilio_call_values()
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required Twilio call configuration: {joined}")

    plan = build_call_plan(
        settings,
        to_number,
        scenario_id,
        call_id=call_id,
        call_type=call_type,
        call_dir_name=call_dir_name,
    )

    try:
        from twilio.rest import Client
    except ImportError as exc:
        raise RuntimeError("Install project dependencies before placing calls.") from exc

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    call_kwargs = {
        "to": plan["to"],
        "from_": plan["from"],
        "url": plan["url"],
        "record": plan["record"],
        "recording_status_callback": plan["recording_status_callback"],
        "recording_status_callback_event": ["completed"],
    }
    call = client.calls.create(**call_kwargs)
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
