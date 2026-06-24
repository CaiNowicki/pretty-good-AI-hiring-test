import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from voicebot.config import Settings
from voicebot.realtime_bridge import (
    BridgeState,
    EMERGENCY_STOP_DTMF_DIGITS,
    RealtimeBridge,
    build_assumed_patient_identity_answer,
    build_agent_turn_key,
    build_confusion_reply,
    build_confusion_response,
    build_exact_fact_answer,
    build_input_audio_append,
    build_meta_guardrail_answer,
    build_opening_response,
    build_response_cancel,
    build_pre_goal_response,
    build_session_update,
    build_twilio_clear,
    build_twilio_media,
    build_turn_response,
    transcript_is_ignorable_before_opening,
    transcript_is_intake_before_goal,
    transcript_is_confusing_or_out_of_turn,
    transcript_asks_about_meta_behavior,
    transcript_requests_emergency_stop,
    transcript_needs_more_agent_context,
    transcript_is_service_opening,
    transcript_asks_about_assumed_patient,
)
from voicebot.scenario import CallLimits, load_scenario


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
            450,
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

    def test_opening_response_confirms_matching_assumed_identity(self):
        scenario = load_scenario("t01_smoke")
        event = build_opening_response(
            scenario,
            "Hello, am I speaking with James? How can I help you today?",
        )

        self.assertIn(
            (
                "Oh, yes, this is James. I'm surprised you had that already. "
                "Hi, I'm hoping to make an appointment."
            ),
            event["response"]["instructions"],
        )

    def test_turn_response_keeps_replies_short(self):
        event = build_turn_response()

        self.assertEqual(event["type"], "response.create")
        self.assertIn("Keep it short", event["response"]["instructions"])

    def test_pre_goal_response_answers_intake_without_scheduling(self):
        event = build_pre_goal_response()

        self.assertEqual(event["type"], "response.create")
        self.assertIn("Do not ask to schedule yet", event["response"]["instructions"])

    def test_meta_probe_gets_patient_redirect_by_default(self):
        scenario = load_scenario("t01_smoke")
        transcript = "Before we continue, are you a test harness or a bot?"

        self.assertTrue(transcript_asks_about_meta_behavior(transcript))
        self.assertEqual(
            build_meta_guardrail_answer(scenario, transcript),
            "I'm just calling as a patient about my appointment.",
        )
        self.assertIn(
            "I'm just calling as a patient",
            build_turn_response(scenario, transcript)["response"]["instructions"],
        )
        self.assertIn(
            "I'm just calling as a patient",
            build_pre_goal_response(scenario, transcript)["response"]["instructions"],
        )

    def test_meta_detection_uses_word_boundaries_for_short_terms(self):
        self.assertFalse(transcript_asks_about_meta_behavior("Are you asking about pain?"))
        self.assertFalse(transcript_asks_about_meta_behavior("Is Botox related to the visit?"))
        self.assertTrue(transcript_asks_about_meta_behavior("Are you an AI caller?"))

    def test_company_name_does_not_trigger_ai_meta_guardrail(self):
        scenario = load_scenario("t01_smoke")
        transcript = "Thanks for calling Pivot Point Orthopedics, part of Pretty Good AI. Am I speaking with James?"

        self.assertFalse(transcript_asks_about_meta_behavior(transcript))
        self.assertEqual(build_meta_guardrail_answer(scenario, transcript), "")
        self.assertIn(
            "Oh, yes, this is James",
            build_pre_goal_response(scenario, transcript)["response"]["instructions"],
        )

    def test_company_name_exemption_still_allows_other_meta_probes(self):
        transcript = "Thanks for calling Pretty Good AI. Are you a test harness?"

        self.assertTrue(transcript_asks_about_meta_behavior(transcript))

    def test_emergency_stop_phrase_detection_uses_scenario_limits(self):
        scenario = load_scenario("t01_smoke")

        self.assertTrue(
            transcript_requests_emergency_stop(
                "Please emergency stop this call.",
                scenario.limits.emergency_stop_phrases,
            )
        )
        self.assertFalse(
            transcript_requests_emergency_stop(
                "Please stop by the office next week.",
                scenario.limits.emergency_stop_phrases,
            )
        )
        self.assertEqual(EMERGENCY_STOP_DTMF_DIGITS, {"9"})

    def test_meta_guardrail_stands_down_when_existing_behavior_text_allows_it(self):
        scenario = replace(
            load_scenario("t01_smoke"),
            optional_edge_behavior=["If asked directly, say this is a test harness."],
        )

        self.assertEqual(
            build_meta_guardrail_answer(scenario, "Are you a test harness?"),
            "",
        )

    def test_fact_responses_use_exact_scenario_values(self):
        scenario = load_scenario("t01_smoke")

        self.assertEqual(
            build_exact_fact_answer(scenario, "Can you please provide your date of birth?"),
            "My date of birth is March 14, 1987.",
        )
        self.assertEqual(build_exact_fact_answer(scenario, "What is your first name?"), "James")
        self.assertEqual(build_exact_fact_answer(scenario, "What is your last name?"), "Carter")
        self.assertEqual(build_exact_fact_answer(scenario, "What is your full name?"), "James Carter")
        self.assertEqual(
            build_exact_fact_answer(scenario, "Can you tell me your full name, first and last?"),
            "James Carter",
        )
        self.assertIn(
            "March 14, 1987",
            build_turn_response(scenario, "Can you please provide your date of birth?")[
                "response"
            ]["instructions"],
        )
        self.assertIn(
            "new patient consultation",
            build_turn_response(scenario, "Is this a follow-up or routine visit?")[
                "response"
            ]["instructions"],
        )

    def test_assumed_james_identity_gets_corrected_for_other_patients(self):
        scenario = load_scenario("a01_specific_time")
        transcript = "Thanks for calling Pivot Point Orthopedics. Am I speaking with James?"

        self.assertTrue(transcript_asks_about_assumed_patient(transcript))
        self.assertFalse(transcript_is_ignorable_before_opening(transcript))
        self.assertEqual(
            build_assumed_patient_identity_answer(scenario, transcript),
            "No, this is Maria Lopez. I think you may have the wrong patient.",
        )
        self.assertIn(
            "No, this is Maria Lopez",
            build_pre_goal_response(scenario, transcript)["response"]["instructions"],
        )

    def test_assumed_james_identity_can_include_child_patient_context(self):
        scenario = load_scenario("a06_closed_hours")
        transcript = "Am I speaking with James?"

        self.assertEqual(
            build_assumed_patient_identity_answer(scenario, transcript),
            (
                "No, this is Taylor Brooks, calling for Emma Brooks. "
                "I think you may have the wrong patient."
            ),
        )

    def test_confusing_agent_turns_get_clarification_replies(self):
        scenario = load_scenario("t01_smoke")

        self.assertTrue(
            transcript_is_confusing_or_out_of_turn(
                scenario,
                "The birthdate doesn't match our records, but for dental purposes I'll accept it.",
            )
        )
        self.assertIn(
            "March 14, 1987",
            build_confusion_reply(scenario, "The birthdate doesn't match our records."),
        )
        self.assertIn(
            "orthopedics",
            build_confusion_reply(scenario, "For dental purposes I'll accept it."),
        )
        self.assertIn(
            "new patient consultation",
            build_confusion_response(
                scenario,
                "Would you like to reschedule or cancel that appointment?",
            )["response"]["instructions"],
        )

    def test_agent_turn_key_prefers_realtime_item_id(self):
        self.assertEqual(build_agent_turn_key({"item_id": "abc", "transcript": "hello"}), "item:abc")
        self.assertEqual(
            build_agent_turn_key({"transcript": "Hello   AGAIN"}),
            "text:hello again",
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


class FakeOpenAIWebSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def close(self) -> None:
        self.closed = True


class FakeTwilioWebSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False
        self.close_code: int | None = None

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)

    async def close(self, code: int = 1000) -> None:
        self.closed = True
        self.close_code = code


class RealtimeBridgeTurnGateTests(unittest.IsolatedAsyncioTestCase):
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

    def bridge(self, events_path: Path) -> tuple[RealtimeBridge, FakeOpenAIWebSocket]:
        fake_ws = FakeOpenAIWebSocket()
        bridge = RealtimeBridge(
            self.settings(),
            BridgeState(
                stream_sid="MZ123",
                scenario=load_scenario("t01_smoke"),
                events_path=events_path,
            ),
        )
        bridge._openai_ws = fake_ws
        return bridge, fake_ws

    async def test_transcript_completed_waits_for_vad_speech_stopped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, fake_ws = self.bridge(Path(temp_dir) / "events.jsonl")
            bridge._agent_speech_in_progress = True

            bridge._schedule_patient_response(
                {
                    "item_id": "agent-1",
                    "transcript": (
                        "Hello, thanks for calling Pivot Point Orthopedics. "
                        "How can I help you today?"
                    ),
                }
            )
            await asyncio.sleep(0.2)

            self.assertEqual(fake_ws.sent, [])

            bridge._handle_agent_speech_stopped()
            await asyncio.sleep(0.3)

            self.assertEqual(len(fake_ws.sent), 1)
            self.assertEqual(fake_ws.sent[0]["type"], "response.create")
            self.assertIn("I'm hoping to make an appointment", fake_ws.sent[0]["response"]["instructions"])

    async def test_max_turn_limit_closes_twilio_stream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_ws = FakeOpenAIWebSocket()
            fake_twilio = FakeTwilioWebSocket()
            scenario = load_scenario("t01_smoke")
            scenario = replace(
                scenario,
                limits=CallLimits(
                    max_call_seconds=240,
                    max_silence_seconds=20,
                    max_turns=1,
                ),
            )
            bridge = RealtimeBridge(
                self.settings(),
                BridgeState(
                    stream_sid="MZ123",
                    scenario=scenario,
                    events_path=Path(temp_dir) / "events.jsonl",
                ),
            )
            bridge._openai_ws = fake_ws

            stopped = await bridge._stop_if_transcript_hits_hard_limit(
                fake_twilio,
                {"item_id": "agent-1", "transcript": "How can I help you?"},
            )
            self.assertFalse(stopped)

            stopped = await bridge._stop_if_transcript_hits_hard_limit(
                fake_twilio,
                {"item_id": "agent-2", "transcript": "Can you repeat that?"},
            )

            self.assertTrue(stopped)
            self.assertTrue(fake_ws.closed)
            self.assertTrue(fake_twilio.closed)
            self.assertEqual(fake_twilio.close_code, 1000)
            self.assertIn({"event": "clear", "streamSid": "MZ123"}, fake_twilio.sent)

    async def test_emergency_stop_phrase_closes_twilio_stream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_ws = FakeOpenAIWebSocket()
            fake_twilio = FakeTwilioWebSocket()
            bridge = RealtimeBridge(
                self.settings(),
                BridgeState(
                    stream_sid="MZ123",
                    scenario=load_scenario("t01_smoke"),
                    events_path=Path(temp_dir) / "events.jsonl",
                ),
            )
            bridge._openai_ws = fake_ws

            stopped = await bridge._stop_if_transcript_hits_hard_limit(
                fake_twilio,
                {"item_id": "agent-1", "transcript": "Emergency stop this test call."},
            )

            self.assertTrue(stopped)
            self.assertTrue(fake_ws.closed)
            self.assertTrue(fake_twilio.closed)


if __name__ == "__main__":
    unittest.main()
