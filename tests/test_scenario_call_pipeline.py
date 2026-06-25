import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from voicebot.artifacts import append_jsonl
from voicebot.config import Settings
from voicebot.constants import ALLOWED_DESTINATION
from voicebot.scenario_call_pipeline import (
    prepare_scenario_call,
    prepare_scenario_call_batch,
    run_scenario_call_batch,
    run_scenario_call,
    write_transcript_from_events,
)


class ScenarioCallPipelineTests(unittest.TestCase):
    def settings(self) -> Settings:
        return Settings(
            twilio_account_sid="ACxxx",
            twilio_auth_token="secret",
            twilio_from_number="+19418420514",
            public_base_url="https://example.ngrok-free.dev",
            openai_api_key="sk-test",
            realtime_model="gpt-realtime-2",
            transcription_model="gpt-4o-transcribe",
        )

    def test_prepares_grouped_call_artifacts_without_creating_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            prepared = prepare_scenario_call(
                self.settings(),
                "a01_specific_time",
                calls_root=Path(temp_dir) / "calls",
            )

            self.assertEqual(prepared.call_type, "appointment_scheduling")
            self.assertEqual(prepared.call_id, "appointment_scheduling-call-001")
            self.assertEqual(
                prepared.call_dir,
                Path(temp_dir) / "calls" / "appointment_scheduling" / "call-001",
            )
            self.assertTrue((prepared.call_dir / "scenario.yaml").exists())
            self.assertTrue((prepared.call_dir / "events.jsonl").exists())
            self.assertFalse((prepared.call_dir / "recording.mp3").exists())

            metadata = json.loads((prepared.call_dir / "metadata.json").read_text())
            self.assertEqual(metadata["status"], "planned")
            self.assertEqual(metadata["review_state"], "not_started")
            self.assertFalse(metadata["call_execution"]["enabled"])
            self.assertFalse(metadata["call_execution"]["twilio_call_created"])
            self.assertIsNone(metadata["call_execution"]["twilio_call_sid"])
            self.assertEqual(metadata["call_plan"]["to"], ALLOWED_DESTINATION)
            self.assertTrue(metadata["call_plan"]["record"])
            self.assertEqual(metadata["call_plan"]["scenario_id"], "a01_specific_time")
            self.assertEqual(
                metadata["artifact_requirements"]["recording_mp3_or_ogg"],
                "pending_call_completion",
            )
            self.assertIn("recording_status_callback", metadata["call_plan"])
            self.assertIn("call_id=appointment_scheduling-call-001", metadata["call_plan"]["url"])
            self.assertIn(
                "call_dir_name=call-001",
                metadata["call_plan"]["recording_status_callback"],
            )

            events = (prepared.call_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"event": "call.boundary"', events)
            self.assertIn('"boundary": "prepared"', events)
            self.assertIn('"calls_enabled": false', events)

    def test_batch_numbers_calls_within_each_scenario_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            prepared = prepare_scenario_call_batch(
                self.settings(),
                ["a01_specific_time", "a02_change_of_mind", "m01_standard_refill"],
                calls_root=Path(temp_dir) / "calls",
            )

            self.assertEqual(
                [item.call_id for item in prepared],
                [
                    "appointment_scheduling-call-001",
                    "appointment_scheduling-call-002",
                    "medication_refill-call-001",
                ],
            )
            self.assertTrue(
                (Path(temp_dir) / "calls" / "appointment_scheduling" / "call-002").exists()
            )
            self.assertTrue((Path(temp_dir) / "calls" / "medication_refill" / "call-001").exists())

    def test_run_scenario_call_starts_live_call_after_preparing_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "voicebot.scenario_call_pipeline.create_outbound_call",
                return_value={
                    "sid": "CA123",
                    "status": "queued",
                    "plan": {},
                    "settings": {},
                },
            ) as create_call:
                prepared = run_scenario_call(
                    self.settings(),
                    "a01_specific_time",
                    live=True,
                    calls_root=Path(temp_dir) / "calls",
                )

            create_call.assert_called_once()
            _, _, scenario_stem = create_call.call_args.args
            self.assertEqual(scenario_stem, "a01_specific_time")
            self.assertEqual(create_call.call_args.kwargs["call_id"], prepared.call_id)
            self.assertEqual(create_call.call_args.kwargs["call_type"], prepared.call_type)
            self.assertEqual(create_call.call_args.kwargs["call_dir_name"], "call-001")

            metadata = json.loads((prepared.call_dir / "metadata.json").read_text())
            self.assertEqual(metadata["status"], "in_progress")
            self.assertTrue(metadata["call_execution"]["enabled"])
            self.assertTrue(metadata["call_execution"]["twilio_call_created"])
            self.assertEqual(metadata["call_execution"]["twilio_call_sid"], "CA123")
            self.assertEqual(
                metadata["artifact_requirements"]["recording_mp3_or_ogg"],
                "pending_recording_callback",
            )

    def test_run_scenario_call_batch_starts_live_calls_in_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "voicebot.scenario_call_pipeline.create_outbound_call",
                side_effect=[
                    {"sid": "CA111", "status": "queued", "plan": {}, "settings": {}},
                    {"sid": "CA222", "status": "queued", "plan": {}, "settings": {}},
                ],
            ) as create_call:
                prepared = run_scenario_call_batch(
                    self.settings(),
                    ["a01_specific_time", "m01_standard_refill"],
                    live=True,
                    calls_root=Path(temp_dir) / "calls",
                )

            self.assertEqual(
                [item.scenario_stem for item in prepared],
                ["a01_specific_time", "m01_standard_refill"],
            )
            self.assertEqual(create_call.call_count, 2)
            self.assertEqual(create_call.call_args_list[0].args[2], "a01_specific_time")
            self.assertEqual(create_call.call_args_list[1].args[2], "m01_standard_refill")

    def test_write_transcript_from_events_creates_speaker_labeled_transcript(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            prepared = prepare_scenario_call(
                self.settings(),
                "t01_smoke",
                calls_root=Path(temp_dir) / "calls",
            )
            append_jsonl(
                prepared.events_path,
                {
                    "event": "openai",
                    "payload": {
                        "type": "conversation.item.input_audio_transcription.completed",
                        "transcript": "How may I help you today?",
                    },
                },
            )
            append_jsonl(
                prepared.events_path,
                {
                    "event": "openai",
                    "payload": {
                        "type": "response.output_audio_transcript.done",
                        "transcript": "Hi, I'm hoping to make an appointment.",
                    },
                },
            )

            transcript_path = write_transcript_from_events(prepared.events_path)

            self.assertEqual(transcript_path, prepared.transcript_path)
            self.assertEqual(
                transcript_path.read_text(encoding="utf-8"),
                (
                    "PGAI Agent: How may I help you today?\n"
                    "Patient Bot: Hi, I'm hoping to make an appointment.\n"
                ),
            )
            metadata = json.loads((prepared.call_dir / "metadata.json").read_text())
            self.assertEqual(metadata["artifact_requirements"]["transcript_txt"], "created")


if __name__ == "__main__":
    unittest.main()
