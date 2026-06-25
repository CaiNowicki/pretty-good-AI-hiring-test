"""OpenAI Realtime API session and audio event constructors."""

from __future__ import annotations

from typing import Any

from voicebot.config import Settings
from voicebot.scenario_loader import Scenario


OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"


PCMU_FORMAT = {"type": "audio/pcmu"}


DEFAULT_PREFIX_PADDING_MS = 500


DEFAULT_SILENCE_DURATION_MS = 450


INTERRUPTION_PREFIX_PADDING_MS = 300


INTERRUPTION_SILENCE_DURATION_MS = 650


def build_openai_realtime_url(settings: Settings) -> str:
    return f"{OPENAI_REALTIME_URL}?model={settings.realtime_model}"


def build_session_update(
    settings: Settings,
    scenario: Scenario,
    system_prompt: str,
) -> dict[str, Any]:
    prefix_padding_ms = (
        INTERRUPTION_PREFIX_PADDING_MS if scenario.interruption_test else DEFAULT_PREFIX_PADDING_MS
    )
    silence_duration_ms = (
        INTERRUPTION_SILENCE_DURATION_MS
        if scenario.interruption_test
        else DEFAULT_SILENCE_DURATION_MS
    )
    return {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": settings.realtime_model,
            "instructions": system_prompt,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": PCMU_FORMAT,
                    "transcription": {"model": settings.transcription_model},
                    "turn_detection": {
                        "type": "server_vad",
                        "create_response": False,
                        "interrupt_response": True,
                        "prefix_padding_ms": prefix_padding_ms,
                        "silence_duration_ms": silence_duration_ms,
                        "idle_timeout_ms": 10000,
                    },
                },
                "output": {
                    "format": PCMU_FORMAT,
                    "voice": "marin",
                },
            },
            "max_output_tokens": 1200,
        },
    }


def build_input_audio_append(payload: str) -> dict[str, str]:
    return {"type": "input_audio_buffer.append", "audio": payload}


def build_response_cancel() -> dict[str, str]:
    return {"type": "response.cancel"}
