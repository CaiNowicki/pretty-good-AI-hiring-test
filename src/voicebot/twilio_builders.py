"""Pure Twilio call-plan and media wire-message constructors."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from voicebot.config import Settings
from voicebot.safety import validate_destination


def _call_query(
    scenario_id: str,
    *,
    call_id: str = "",
    call_type: str = "",
    call_dir_name: str = "",
) -> str:
    params = {"scenario_id": scenario_id}
    if call_id:
        params["call_id"] = call_id
    if call_type:
        params["call_type"] = call_type
    if call_dir_name:
        params["call_dir_name"] = call_dir_name
    return urlencode(params)


def build_voice_webhook_url(
    settings: Settings,
    scenario_id: str,
    *,
    call_id: str = "",
    call_type: str = "",
    call_dir_name: str = "",
) -> str:
    query = _call_query(
        scenario_id,
        call_id=call_id,
        call_type=call_type,
        call_dir_name=call_dir_name,
    )
    return f"{settings.public_base_url.rstrip('/')}/twilio/voice?{query}"


def build_recording_status_callback_url(
    settings: Settings,
    scenario_id: str,
    *,
    call_id: str = "",
    call_type: str = "",
    call_dir_name: str = "",
) -> str:
    query = _call_query(
        scenario_id,
        call_id=call_id,
        call_type=call_type,
        call_dir_name=call_dir_name,
    )
    return f"{settings.public_base_url.rstrip('/')}/twilio/recording?{query}"


def build_call_plan(
    settings: Settings,
    to_number: str,
    scenario_id: str,
    *,
    call_id: str = "",
    call_type: str = "",
    call_dir_name: str = "",
) -> dict[str, Any]:
    destination = validate_destination(to_number)
    return {
        "to": destination,
        "from": settings.twilio_from_number,
        "url": build_voice_webhook_url(
            settings,
            scenario_id,
            call_id=call_id,
            call_type=call_type,
            call_dir_name=call_dir_name,
        ),
        "record": True,
        "recording_status_callback": build_recording_status_callback_url(
            settings,
            scenario_id,
            call_id=call_id,
            call_type=call_type,
            call_dir_name=call_dir_name,
        ),
        "scenario_id": scenario_id,
        "call_id": call_id,
        "call_type": call_type,
        "call_dir_name": call_dir_name,
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
