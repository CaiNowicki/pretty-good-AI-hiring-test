import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voicebot.artifacts import DEFAULT_CALLS_ROOT
from voicebot.config import Settings
from voicebot.server import _call_events_path, health, twilio_voice


def settings(public_base_url: str) -> Settings:
    return Settings(
        twilio_account_sid="ACxxx",
        twilio_auth_token="secret",
        twilio_from_number="+19418420514",
        public_base_url=public_base_url,
        openai_api_key="sk-test",
        realtime_model="gpt-realtime-2",
        transcription_model="gpt-4o-transcribe",
    )


class ServerTests(unittest.TestCase):
    def test_voice_twiml_uses_absolute_websocket_url(self):
        with patch("voicebot.server.load_settings", return_value=settings("https://current-tunnel.example")):
            response = twilio_voice(scenario_id="t01_smoke")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            '<Stream url="wss://current-tunnel.example/twilio/media">',
            response.body.decode("utf-8"),
        )

    def test_voice_twiml_accepts_composed_patient_scenario_id(self):
        with patch("voicebot.server.load_settings", return_value=settings("https://current-tunnel.example")):
            response = twilio_voice(scenario_id="m01_standard_refill__patient_carmen_reyes")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'name="scenario_id" value="m01_standard_refill__patient_carmen_reyes"',
            response.body.decode("utf-8"),
        )

    def test_voice_twiml_fails_clearly_for_unknown_scenario(self):
        with patch("voicebot.server.load_settings", return_value=settings("https://current-tunnel.example")):
            response = twilio_voice(scenario_id="missing_scenario")

        self.assertEqual(response.status_code, 404)
        self.assertIn("No scenario found", response.body.decode("utf-8"))

    def test_voice_twiml_fails_clearly_without_public_base_url(self):
        with patch("voicebot.server.load_settings", return_value=settings("")):
            response = twilio_voice(scenario_id="t01_smoke")

        self.assertEqual(response.status_code, 500)
        self.assertIn("Missing PUBLIC_BASE_URL", response.body.decode("utf-8"))

    def test_health_reports_media_stream_configuration(self):
        with patch("voicebot.server.load_settings", return_value=settings("https://current-tunnel.example")):
            response = health()

        self.assertTrue(response["public_base_url_configured"])
        self.assertEqual(
            response["media_stream_url"],
            "wss://current-tunnel.example/twilio/media",
        )

    def test_call_events_path_is_not_relative_to_process_cwd(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                os.chdir(temp_dir)
                path = _call_events_path(
                    call_type="orthopedic_edge_cases",
                    call_dir_name="call-006",
                )
            finally:
                os.chdir(original_cwd)

        self.assertEqual(
            path,
            DEFAULT_CALLS_ROOT / "orthopedic_edge_cases" / "call-006" / "events.jsonl",
        )


if __name__ == "__main__":
    unittest.main()
