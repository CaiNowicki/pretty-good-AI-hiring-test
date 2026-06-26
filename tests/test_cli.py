import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from voicebot.artifacts import DEFAULT_CALLS_ROOT
from voicebot.cli import main


class CliTests(unittest.TestCase):
    def write_env(self) -> str:
        handle = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        with handle as env_file:
            env_file.write("TWILIO_ACCOUNT_SID=ACxxx\n")
            env_file.write("TWILIO_AUTH_TOKEN=secret\n")
            env_file.write("TWILIO_FROM_NUMBER=+15551234567\n")
            env_file.write("PUBLIC_BASE_URL=https://current-tunnel.example\n")
            env_file.write("OPENAI_API_KEY=sk-test\n")
        return handle.name

    def test_help_command_prints_reduced_command_surface(self):
        output = io.StringIO()

        with redirect_stdout(output):
            result = main(["help"])

        self.assertEqual(result, 0)
        help_text = output.getvalue()
        self.assertIn("pgai-call a01_specific_time --live", help_text)
        self.assertIn("pgai-call appointment-scheduling --batch --live", help_text)
        self.assertIn("pgai-call all-scenarios --live", help_text)
        self.assertIn("pgai-call config --list-scenarios", help_text)

    def test_config_lists_scenarios_and_reports_ready(self):
        output = io.StringIO()
        env_path = self.write_env()

        try:
            with redirect_stdout(output):
                result = main(["config", "--env-file", env_path, "--list-scenarios"])
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(result, 0)
        self.assertIn("Ready for live calls.", output.getvalue())
        self.assertIn("appointment-scheduling:", output.getvalue())
        self.assertIn("a01_specific_time:", output.getvalue())

    def test_config_returns_nonzero_when_required_values_are_missing(self):
        output = io.StringIO()

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as env_file:
            env_file.write("TWILIO_FROM_NUMBER=+15551234567\n")
            env_path = env_file.name

        try:
            with redirect_stdout(output):
                result = main(["config", "--env-file", env_path])
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(result, 1)
        self.assertIn("Missing values:", output.getvalue())
        self.assertIn("TWILIO_ACCOUNT_SID", output.getvalue())
        self.assertIn("OPENAI_API_KEY", output.getvalue())

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

    def test_scenario_target_requires_live(self):
        with self.assertRaises(SystemExit) as raised:
            main(["a01_specific_time"])

        self.assertEqual(raised.exception.code, 2)

    def test_specific_scenario_live_uses_project_absolute_artifacts_root(self):
        output = io.StringIO()
        env_path = self.write_env()
        prepared = SimpleNamespace(
            call_id="appointment_scheduling-call-001",
            call_dir=DEFAULT_CALLS_ROOT / "appointment_scheduling" / "call-001",
            runtime_scenario_id="a01_specific_time",
        )

        try:
            with patch("voicebot.cli.run_scenario_call", return_value=prepared) as run_call:
                with redirect_stdout(output):
                    result = main(["a01_specific_time", "--live", "--yes", "--env-file", env_path])
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(result, 0)
        self.assertEqual(run_call.call_args.args[1], "a01_specific_time")
        self.assertTrue(run_call.call_args.kwargs["live"])
        self.assertEqual(run_call.call_args.kwargs["calls_root"], DEFAULT_CALLS_ROOT)
        self.assertIn("Started live scenario call", output.getvalue())

    def test_all_scenarios_live_starts_limited_twilio_series(self):
        output = io.StringIO()
        env_path = self.write_env()

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
                                "all-scenarios",
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
        self.assertIn("Started 1/2:", output.getvalue())
        self.assertIn("Started 2/2:", output.getvalue())
        self.assertIn("Started live scenario batch through Twilio", output.getvalue())

    def test_all_scenarios_live_defaults_to_completion_wait(self):
        output = io.StringIO()
        env_path = self.write_env()

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
                                    "all-scenarios",
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

    def test_group_live_without_batch_runs_one_randomized_scenario(self):
        output = io.StringIO()
        env_path = self.write_env()
        prepared = SimpleNamespace(
            call_id="information_gathering-call-001",
            call_dir=Path("artifacts/calls/information_gathering/call-001"),
            runtime_scenario_id="i01_office_hours__patient_maya_patel",
        )

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                calls_root = Path(temp_dir) / "calls"
                with patch("voicebot.cli.run_scenario_call", return_value=prepared) as run_call:
                    with redirect_stdout(output):
                        result = main(
                            [
                                "information-gathering",
                                "--live",
                                "--shuffle-seed",
                                "unit-test",
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
        run_call.assert_called_once()
        self.assertTrue(run_call.call_args.args[1].startswith("i"))
        self.assertTrue(run_call.call_args.args[1].find("__patient_") > 0)
        self.assertTrue(run_call.call_args.kwargs["live"])
        self.assertIn("Started live scenario call", output.getvalue())

    def test_group_batch_uses_only_that_group(self):
        output = io.StringIO()
        env_path = self.write_env()

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                calls_root = Path(temp_dir) / "calls"
                with patch(
                    "voicebot.cli.run_scenario_call_batch",
                    return_value=[],
                ) as run_batch:
                    with redirect_stdout(output):
                        result = main(
                            [
                                "information-gathering",
                                "--batch",
                                "--live",
                                "--shuffle-seed",
                                "unit-test",
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
        scenario_ids = run_batch.call_args.args[1]
        self.assertEqual(len(scenario_ids), 5)
        self.assertTrue(all(scenario_id.startswith("i") for scenario_id in scenario_ids))
        self.assertTrue(all("__patient_" in scenario_id for scenario_id in scenario_ids))
        self.assertIn("Started live scenario batch through Twilio", output.getvalue())

    def test_difficult_group_no_longer_folds_in_edge_case_scenarios(self):
        env_path = self.write_env()

        try:
            with patch("voicebot.cli.run_scenario_call_batch", return_value=[]) as run_batch:
                result = main(
                    [
                        "difficult-call-handling",
                        "--batch",
                        "--live",
                        "--yes",
                        "--env-file",
                        env_path,
                    ]
                )
        finally:
            Path(env_path).unlink(missing_ok=True)

        self.assertEqual(result, 0)
        scenario_ids = run_batch.call_args.args[1]
        self.assertEqual(len(scenario_ids), 4)
        self.assertTrue(all(scenario_id.startswith("d") for scenario_id in scenario_ids))

    def test_legacy_dry_run_command_is_removed(self):
        with self.assertRaises(SystemExit) as raised:
            main(["dry-run", "--scenario", "t01_smoke"])

        self.assertEqual(raised.exception.code, 2)

    def test_legacy_dev_mode_is_removed(self):
        with self.assertRaises(SystemExit) as raised:
            main(["a01_specific_time", "dev"])

        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
