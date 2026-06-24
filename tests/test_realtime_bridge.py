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
    build_repeated_info_answer,
    build_response_cancel,
    build_pre_goal_response,
    build_session_update,
    build_twilio_clear,
    build_twilio_media,
    build_turn_response,
    repeated_info_probability,
    requested_info_key,
    should_point_out_repeated_info,
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
        self.assertIn("Maya Patel", event["session"]["instructions"])

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
            "Hello, am I speaking with Maya? How can I help you today?",
        )

        self.assertIn(
            (
                "Oh, yes, this is Maya. I'm surprised you had that already. "
                "Hi, I'm hoping to make an appointment."
            ),
            event["response"]["instructions"],
        )

    def test_turn_response_keeps_replies_short(self):
        event = build_turn_response()

        self.assertEqual(event["type"], "response.create")
        self.assertIn("Keep it short", event["response"]["instructions"])
        self.assertIn("demos", event["response"]["instructions"])
        self.assertIn("Stay in the patient role", event["response"]["instructions"])
        self.assertIn("'let me check'", event["response"]["instructions"])
        self.assertIn("'Could you check that for me?'", event["response"]["instructions"])

    def test_pre_goal_response_answers_intake_without_scheduling(self):
        event = build_pre_goal_response()

        self.assertEqual(event["type"], "response.create")
        self.assertIn("Do not ask to schedule yet", event["response"]["instructions"])
        self.assertIn("demos", event["response"]["instructions"])
        self.assertIn("Stay in the patient role", event["response"]["instructions"])
        self.assertIn("'I can schedule you'", event["response"]["instructions"])
        self.assertIn("'That works for me if you can book it'", event["response"]["instructions"])

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
        transcript = "Thanks for calling Pivot Point Orthopedics, part of Pretty Good AI. Am I speaking with Maya?"

        self.assertFalse(transcript_asks_about_meta_behavior(transcript))
        self.assertEqual(build_meta_guardrail_answer(scenario, transcript), "")
        self.assertIn(
            "Oh, yes, this is Maya",
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
        self.assertEqual(
            build_exact_fact_answer(scenario, "1987?"),
            "Yes, my date of birth is March 14, 1987.",
        )
        self.assertEqual(build_exact_fact_answer(scenario, "1987."), "")
        self.assertEqual(build_exact_fact_answer(scenario, "What is your first name?"), "Maya")
        self.assertEqual(build_exact_fact_answer(scenario, "What is your last name?"), "Patel")
        self.assertEqual(build_exact_fact_answer(scenario, "What is your full name?"), "Maya Patel")
        self.assertEqual(build_exact_fact_answer(scenario, "Can I have your name?"), "Maya Patel")
        self.assertEqual(
            build_exact_fact_answer(scenario, "Can you spell your first name?"),
            "M-A-Y-A",
        )
        self.assertEqual(
            build_exact_fact_answer(scenario, "Can you spell your last name?"),
            "P-A-T-E-L",
        )
        self.assertEqual(
            build_exact_fact_answer(scenario, "How do you spell your name?"),
            "M-A-Y-A P-A-T-E-L",
        )
        self.assertEqual(
            build_exact_fact_answer(scenario, "Can you spell your first and last name?"),
            "M-A-Y-A P-A-T-E-L",
        )
        self.assertEqual(
            build_exact_fact_answer(scenario, "Can you tell me your full name, first and last?"),
            "Maya Patel",
        )
        provider_answer = build_exact_fact_answer(
            scenario,
            "Do you have a specific provider you'd like to see or is this for a new patient consultation?",
        )
        self.assertIn("provider", provider_answer.casefold())
        self.assertTrue(
            "no preference" in provider_answer.casefold()
            or "don't have" in provider_answer.casefold()
        )
        self.assertNotIn("new patient consultation", provider_answer.casefold())
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
        appointment_type_answers = {
            build_exact_fact_answer(scenario, prompt)
            for prompt in (
                "Is this a follow-up or routine visit?",
                "What type of appointment are you looking for?",
                "Is this for a new patient consultation?",
                "Can you tell me the reason for visit?",
            )
        }
        self.assertGreater(len(appointment_type_answers), 1)
        for answer in appointment_type_answers:
            self.assertIn("new patient", answer.casefold())
            self.assertIn("consultation", answer.casefold())

    def test_repeated_info_probability_increases_with_repeat_count(self):
        probabilities = [repeated_info_probability(count) for count in range(5)]

        self.assertEqual(probabilities[0], 0.0)
        self.assertEqual(probabilities, sorted(probabilities))
        self.assertGreater(probabilities[-1], probabilities[1])

    def test_repeated_info_helpers_keep_the_fact_in_the_answer(self):
        scenario = load_scenario("t01_smoke")

        self.assertEqual(
            requested_info_key(scenario, "Can you provide your date of birth again?"),
            "date_of_birth",
        )
        self.assertEqual(
            requested_info_key(scenario, "Can you spell your last name again?"),
            "last_name_spelling",
        )
        self.assertEqual(
            requested_info_key(scenario, "Is this a follow-up or routine visit?"),
            "appointment_type",
        )
        self.assertEqual(
            requested_info_key(scenario, "Any preferred provider, or are you open to anyone?"),
            "provider_preference",
        )
        self.assertIn(
            "March 14, 1987",
            build_repeated_info_answer(
                "date_of_birth",
                "My date of birth is March 14, 1987.",
                0,
            ),
        )
        self.assertIn(
            "how to spell my last name",
            build_repeated_info_answer("last_name_spelling", "P-A-T-E-L", 0),
        )

    def test_hyphenated_name_spelling_uses_scenario_override(self):
        scenario = load_scenario("a07_name_lookup_confusion")

        self.assertEqual(
            build_exact_fact_answer(scenario, "Could you spell your last name?"),
            "R-E-Y-E-S hyphen M-O-N-T-O-Y-A",
        )
        self.assertEqual(
            build_exact_fact_answer(scenario, "Could you spell Reyes-Montoya for me?"),
            "R-E-Y-E-S hyphen M-O-N-T-O-Y-A",
        )

    def test_repeated_info_decision_uses_runtime_probability(self):
        self.assertFalse(should_point_out_repeated_info(0, 0.0))
        self.assertFalse(should_point_out_repeated_info(1, 0.26))
        self.assertTrue(should_point_out_repeated_info(1, 0.24))
        self.assertTrue(should_point_out_repeated_info(4, 0.89))

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

    def test_only_matching_persona_confirms_assumed_identity(self):
        maya_scenario = load_scenario("t01_smoke")
        maria_scenario = load_scenario("a01_specific_time")

        self.assertEqual(
            build_assumed_patient_identity_answer(maya_scenario, "Is this Maya?"),
            "Oh, yes, this is Maya. I'm surprised you had that already.",
        )
        self.assertEqual(
            build_assumed_patient_identity_answer(maya_scenario, "Is this James?"),
            "No, this is Maya Patel. I think you may have the wrong patient.",
        )
        self.assertEqual(
            build_assumed_patient_identity_answer(maria_scenario, "Is this James?"),
            "No, this is Maria Lopez. I think you may have the wrong patient.",
        )
        self.assertNotIn(
            "Yes",
            build_assumed_patient_identity_answer(maria_scenario, "Is this James?"),
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
        change_instructions = build_confusion_response(
            scenario,
            "Would you like to reschedule or cancel that appointment?",
        )["response"]["instructions"]
        self.assertNotIn("I don't understand; I'm trying to schedule", change_instructions)
        self.assertIn("appointment", change_instructions.casefold())

    def test_new_patient_existing_appointment_confusion_asks_for_details(self):
        scenario = load_scenario("t01_smoke")
        answer = build_confusion_reply(
            scenario,
            "It looks like you already have a new patient consultation appointment booked.",
        )

        self.assertNotIn("I don't understand; I'm trying to schedule", answer)
        self.assertIn("appointment", answer.casefold())
        self.assertTrue("when" in answer.casefold() or "date" in answer.casefold())

    def test_new_patient_change_prompt_gets_contextual_variant(self):
        scenario = load_scenario("t01_smoke")
        prompts = (
            "Would you like to reschedule or cancel that appointment?",
            "I can help. Would you like to reschedule or cancel your current appointment?",
            "If you want to change the date or time, I can help reschedule or cancel it.",
        )
        answers = {build_confusion_reply(scenario, prompt) for prompt in prompts}

        self.assertGreater(len(answers), 1)
        for answer in answers:
            self.assertNotIn("I don't understand; I'm trying to schedule", answer)
            self.assertIn("appointment", answer.casefold())

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
        self.assertTrue(transcript_needs_more_agent_context("for this demo"))
        self.assertTrue(transcript_needs_more_agent_context("1987."))
        self.assertFalse(transcript_needs_more_agent_context("1987?"))
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


class FakeRandom:
    def __init__(self, random_values: list[float], randrange_values: list[int]):
        self.random_values = list(random_values)
        self.randrange_values = list(randrange_values)

    def random(self) -> float:
        if self.random_values:
            return self.random_values.pop(0)
        return 1.0

    def randrange(self, stop: int) -> int:
        if self.randrange_values:
            return self.randrange_values.pop(0) % stop
        return 0


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

    async def test_pre_goal_partial_agent_turn_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, fake_ws = self.bridge(Path(temp_dir) / "events.jsonl")

            await bridge._maybe_create_patient_response(
                {"item_id": "agent-1", "transcript": "for this demo"}
            )

            self.assertEqual(fake_ws.sent, [])
            events = (Path(temp_dir) / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"reason": "partial_agent_turn"', events)

    async def test_pre_goal_dob_confirmation_is_not_treated_as_fragment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, fake_ws = self.bridge(Path(temp_dir) / "events.jsonl")

            await bridge._maybe_create_patient_response(
                {"item_id": "agent-1", "transcript": "1987?"}
            )

            self.assertEqual(len(fake_ws.sent), 1)
            self.assertIn(
                "Yes, my date of birth is March 14, 1987.",
                fake_ws.sent[0]["response"]["instructions"],
            )

    async def test_repeated_info_callout_probability_and_wording_vary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, fake_ws = self.bridge(Path(temp_dir) / "events.jsonl")
            bridge._random = FakeRandom(
                random_values=[1.0, 0.0, 0.0],
                randrange_values=[0, 0, 0],
            )

            await bridge._maybe_create_patient_response(
                {"item_id": "agent-1", "transcript": "Can you provide your date of birth?"}
            )
            bridge._patient_response_in_progress = False
            await bridge._maybe_create_patient_response(
                {"item_id": "agent-2", "transcript": "Can you provide your date of birth again?"}
            )
            bridge._patient_response_in_progress = False
            await bridge._maybe_create_patient_response(
                {"item_id": "agent-3", "transcript": "Can you repeat your date of birth?"}
            )

            self.assertEqual(len(fake_ws.sent), 3)
            first = fake_ws.sent[0]["response"]["instructions"]
            second = fake_ws.sent[1]["response"]["instructions"]
            third = fake_ws.sent[2]["response"]["instructions"]
            self.assertNotIn("already", first.casefold())
            self.assertIn("March 14, 1987", second)
            self.assertIn("March 14, 1987", third)
            self.assertNotEqual(second, third)

    async def test_pre_goal_service_opening_after_demo_fragment_uses_patient_goal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bridge, fake_ws = self.bridge(Path(temp_dir) / "events.jsonl")

            await bridge._maybe_create_patient_response(
                {"item_id": "agent-1", "transcript": "for this demo"}
            )
            await bridge._maybe_create_patient_response(
                {"item_id": "agent-2", "transcript": "What can I help you with today?"}
            )

            self.assertEqual(len(fake_ws.sent), 1)
            instructions = fake_ws.sent[0]["response"]["instructions"]
            self.assertIn("I'm hoping to make an appointment", instructions)
            self.assertNotIn("demo", instructions.casefold())

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
