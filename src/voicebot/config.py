"""Runtime configuration loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from voicebot.constants import ALLOWED_DESTINATION


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env(name: str, dotenv: dict[str, str], default: str = "") -> str:
    return os.environ.get(name, dotenv.get(name, default)).strip()


@dataclass(frozen=True)
class Settings:
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    public_base_url: str
    openai_api_key: str
    realtime_model: str
    transcription_model: str
    allowed_destination: str = ALLOWED_DESTINATION

    @property
    def public_ws_base_url(self) -> str:
        base = self.public_base_url.rstrip("/")
        if base.startswith("https://"):
            return "wss://" + base[len("https://") :]
        if base.startswith("http://"):
            return "ws://" + base[len("http://") :]
        return base

    def missing_twilio_call_values(self) -> list[str]:
        required = {
            "TWILIO_ACCOUNT_SID": self.twilio_account_sid,
            "TWILIO_AUTH_TOKEN": self.twilio_auth_token,
            "TWILIO_FROM_NUMBER": self.twilio_from_number,
            "PUBLIC_BASE_URL": self.public_base_url,
        }
        return [name for name, value in required.items() if not value]


def load_settings(env_file: str | Path = ".env") -> Settings:
    dotenv = _read_dotenv(Path(env_file))
    return Settings(
        twilio_account_sid=_env("TWILIO_ACCOUNT_SID", dotenv),
        twilio_auth_token=_env("TWILIO_AUTH_TOKEN", dotenv),
        twilio_from_number=_env("TWILIO_FROM_NUMBER", dotenv),
        public_base_url=_env("PUBLIC_BASE_URL", dotenv),
        openai_api_key=_env("OPENAI_API_KEY", dotenv),
        realtime_model=_env("REALTIME_MODEL", dotenv, "gpt-realtime-2"),
        transcription_model=_env("TRANSCRIPTION_MODEL", dotenv, "gpt-4o-transcribe"),
    )

