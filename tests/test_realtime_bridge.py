import unittest

from voicebot.config import Settings
from voicebot.realtime_bridge import (
    build_input_audio_append,
    build_opening_response,
    build_session_update,
    build_twilio_media,
)
from voicebot.scenario import load_scenario


class RealtimeBridgeTests(unittest.TestCase):
    def settings(self):
        return Settings(
            twilio_account_sid="ACxxx",
            twilio_auth_token="secret",
            twilio_from_number="+19418420514",
            public_base_url="https://example.ngrok-free.dev",
            openai_api_key="sk-test",
            realtime_model="gpt-realtime-2",
            transcription_model="gpt-4o-transcribe",
        )

    def test_session_update_uses_phone_audio_format(self):
        scenario = load_scenario("t01_smoke")
        event = build_session_update(self.settings(), scenario)

        self.assertEqual(event["type"], "session.update")
        self.assertEqual(event["session"]["type"], "realtime")
        self.assertEqual(event["session"]["audio"]["input"]["format"]["type"], "audio/pcmu")
        self.assertEqual(event["session"]["audio"]["output"]["format"]["type"], "audio/pcmu")
        self.assertEqual(event["session"]["audio"]["input"]["turn_detection"]["type"], "server_vad")
        self.assertIn("James Carter", event["session"]["instructions"])

    def test_opening_response_uses_scenario_line(self):
        scenario = load_scenario("t01_smoke")
        event = build_opening_response(scenario)

        self.assertEqual(event["type"], "response.create")
        self.assertIn(scenario.opening_line, event["response"]["instructions"])

    def test_audio_payload_mapping(self):
        payload = "abc123"

        self.assertEqual(
            build_input_audio_append(payload),
            {"type": "input_audio_buffer.append", "audio": payload},
        )
        self.assertEqual(
            build_twilio_media("MZ123", payload),
            {"event": "media", "streamSid": "MZ123", "media": {"payload": payload}},
        )


if __name__ == "__main__":
    unittest.main()
