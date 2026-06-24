import unittest
from dataclasses import replace

from voicebot.config import Settings
from voicebot.realtime_bridge import (
    build_exact_fact_answer,
    build_input_audio_append,
    build_opening_response,
    build_response_cancel,
    build_pre_goal_response,
    build_session_update,
    build_twilio_clear,
    build_twilio_media,
    build_turn_response,
    transcript_is_ignorable_before_opening,
    transcript_is_intake_before_goal,
    transcript_needs_more_agent_context,
    transcript_is_service_opening,
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
        self.assertFalse(event["session"]["audio"]["input"]["turn_detection"]["create_response"])
        self.assertTrue(event["session"]["audio"]["input"]["turn_detection"]["interrupt_response"])
        self.assertEqual(event["session"]["audio"]["input"]["turn_detection"]["prefix_padding_ms"], 500)
        self.assertEqual(
            event["session"]["audio"]["input"]["turn_detection"]["silence_duration_ms"],
            1200,
        )
        self.assertIn("James Carter", event["session"]["instructions"])

    def test_interruption_test_uses_more_aggressive_turn_detection(self):
        scenario = replace(load_scenario("t01_smoke"), interruption_test=True)
        event = build_session_update(self.settings(), scenario)

        self.assertEqual(event["session"]["audio"]["input"]["turn_detection"]["prefix_padding_ms"], 300)
        self.assertEqual(
            event["session"]["audio"]["input"]["turn_detection"]["silence_duration_ms"],
            650,
        )

    def test_opening_response_uses_scenario_line(self):
        scenario = load_scenario("t01_smoke")
        event = build_opening_response(scenario)

        self.assertEqual(event["type"], "response.create")
        self.assertIn(scenario.opening_line, event["response"]["instructions"])
        self.assertIn("exactly once", event["response"]["instructions"])

    def test_turn_response_keeps_replies_short(self):
        event = build_turn_response()

        self.assertEqual(event["type"], "response.create")
        self.assertIn("Keep it short", event["response"]["instructions"])

    def test_pre_goal_response_answers_intake_without_scheduling(self):
        event = build_pre_goal_response()

        self.assertEqual(event["type"], "response.create")
        self.assertIn("Do not ask to schedule yet", event["response"]["instructions"])

    def test_fact_responses_use_exact_scenario_values(self):
        scenario = load_scenario("t01_smoke")

        self.assertEqual(
            build_exact_fact_answer(scenario, "Can you please provide your date of birth?"),
            "My date of birth is March 14, 1987.",
        )
        self.assertEqual(build_exact_fact_answer(scenario, "What is your first name?"), "James")
        self.assertEqual(build_exact_fact_answer(scenario, "What is your last name?"), "Carter")
        self.assertIn(
            "March 14, 1987",
            build_turn_response(scenario, "Can you please provide your date of birth?")[
                "response"
            ]["instructions"],
        )

    def test_opening_gate_skips_ivr_and_waits_for_service_prompt(self):
        self.assertTrue(transcript_is_ignorable_before_opening("This call may be recorded."))
        self.assertTrue(transcript_is_ignorable_before_opening("Para espanol, oprima el dos."))
        self.assertTrue(transcript_is_ignorable_before_opening("Thank you for calling."))
        self.assertFalse(transcript_is_service_opening("Thank you for calling."))
        self.assertTrue(transcript_is_service_opening("Thank you for calling, how may I help you?"))

    def test_intake_before_goal_is_not_treated_as_service_opening(self):
        transcript = "Would you like to create a demo patient profile with me now?"

        self.assertTrue(transcript_is_intake_before_goal(transcript))
        self.assertFalse(transcript_is_service_opening(transcript))

    def test_partial_agent_turns_wait_for_more_context(self):
        self.assertTrue(transcript_needs_more_agent_context("It looks"))
        self.assertTrue(transcript_needs_more_agent_context("specific provider you'd like to see or"))
        self.assertFalse(transcript_needs_more_agent_context("What would you like to do?"))

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
        self.assertEqual(build_twilio_clear("MZ123"), {"event": "clear", "streamSid": "MZ123"})
        self.assertEqual(build_response_cancel(), {"type": "response.cancel"})


if __name__ == "__main__":
    unittest.main()
