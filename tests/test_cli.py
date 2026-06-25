import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from voicebot.cli import main


class CliTests(unittest.TestCase):
    def test_dev_run_can_delete_scaffold_after_demo_prompt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            calls_root = Path(temp_dir) / "calls"
            output = io.StringIO()

            with patch("builtins.input", side_effect=["DEV", "DELETE"]):
                with redirect_stdout(output):
                    result = main(
                        [
                            "a01_specific_time",
                            "dev",
                            "--calls-root",
                            str(calls_root),
                        ]
                    )

            self.assertEqual(result, 0)
            call_dir = calls_root / "appointment_scheduling" / "call-001"
            self.assertFalse(call_dir.exists())
            self.assertIn("DEV CLEANUP", output.getvalue())
            self.assertIn("Deleted dev artifacts", output.getvalue())

    def test_dev_run_keeps_scaffold_when_cleanup_is_not_confirmed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            calls_root = Path(temp_dir) / "calls"
            output = io.StringIO()

            with patch("builtins.input", side_effect=["DEV", ""]):
                with redirect_stdout(output):
                    result = main(
                        [
                            "a01_specific_time",
                            "dev",
                            "--calls-root",
                            str(calls_root),
                        ]
                    )

            self.assertEqual(result, 0)
            call_dir = calls_root / "appointment_scheduling" / "call-001"
            self.assertTrue(call_dir.exists())
            self.assertIn("Keeping dev artifacts", output.getvalue())

    def test_dry_run_accepts_public_base_url_override(self):
        output = io.StringIO()

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as env_file:
            env_file.write("TWILIO_FROM_NUMBER=+15551234567\n")
            env_path = env_file.name

        try:
            with redirect_stdout(output):
                result = main(
                    [
                        "dry-run",
                        "--env-file",
                        env_path,
                        "--public-base-url",
                        "https://current-tunnel.example",
                    ]
                )
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(result, 0)
        self.assertIn(
            "https://current-tunnel.example/twilio/voice?scenario_id=t01_smoke",
            output.getvalue(),
        )

    def test_server_public_base_url_override_sets_process_env(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("uvicorn.run") as run:
                result = main(
                    [
                        "server",
                        "--public-base-url",
                        "https://current-tunnel.example",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertEqual(
                os.environ["PUBLIC_BASE_URL"],
                "https://current-tunnel.example",
            )
            run.assert_called_once()

    def test_pipeline_live_all_scenarios_starts_limited_twilio_series(self):
        output = io.StringIO()

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as env_file:
            env_file.write("TWILIO_ACCOUNT_SID=ACxxx\n")
            env_file.write("TWILIO_AUTH_TOKEN=secret\n")
            env_file.write("TWILIO_FROM_NUMBER=+15551234567\n")
            env_file.write("PUBLIC_BASE_URL=https://current-tunnel.example\n")
            env_path = env_file.name

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                calls_root = Path(temp_dir) / "calls"
                with patch(
                    "voicebot.scenario_call_pipeline.create_outbound_call",
                    side_effect=[
                        {"sid": "CA111", "status": "queued", "plan": {}, "settings": {}},
                        {"sid": "CA222", "status": "queued", "plan": {}, "settings": {}},
                    ],
                ) as create_call:
                    with redirect_stdout(output):
                        result = main(
                            [
                                "scenario-call-pipeline",
                                "--all-scenarios",
                                "--live",
                                "--limit",
                                "2",
                                "--inter-call-delay-seconds",
                                "0",
                                "--no-wait-for-completion",
                                "--yes",
                                "--env-file",
                                env_path,
                                "--calls-root",
                                str(calls_root),
                            ]
                        )
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(result, 0)
        self.assertEqual(create_call.call_count, 2)
        self.assertIn("Started scenario-call pipeline through Twilio", output.getvalue())

    def test_pipeline_live_all_scenarios_defaults_to_completion_wait(self):
        output = io.StringIO()

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as env_file:
            env_file.write("TWILIO_ACCOUNT_SID=ACxxx\n")
            env_file.write("TWILIO_AUTH_TOKEN=secret\n")
            env_file.write("TWILIO_FROM_NUMBER=+15551234567\n")
            env_file.write("PUBLIC_BASE_URL=https://current-tunnel.example\n")
            env_path = env_file.name

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                calls_root = Path(temp_dir) / "calls"
                with patch(
                    "voicebot.cli.run_scenario_call_batch",
                    return_value=[],
                ) as run_batch:
                    with patch("builtins.input", return_value="LIVE ALL"):
                        with redirect_stdout(output):
                            result = main(
                                [
                                    "scenario-call-pipeline",
                                    "--all-scenarios",
                                    "--live",
                                    "--limit",
                                    "2",
                                    "--env-file",
                                    env_path,
                                    "--calls-root",
                                    str(calls_root),
                                ]
                            )
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(result, 0)
        self.assertTrue(run_batch.call_args.kwargs["wait_for_completion"])
        self.assertEqual(run_batch.call_args.kwargs["inter_call_delay_seconds"], 0.0)
        self.assertIn(
            "Each next call will start after the previous call completes.",
            output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
