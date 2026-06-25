import json
import tempfile
import unittest
from pathlib import Path

from voicebot.config import Settings
from voicebot.constants import ALLOWED_DESTINATION
from voicebot.scenario_call_pipeline import (
    prepare_scenario_call,
    prepare_scenario_call_batch,
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


if __name__ == "__main__":
    unittest.main()
