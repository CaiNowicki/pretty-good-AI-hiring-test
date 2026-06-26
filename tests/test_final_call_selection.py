import json
import tempfile
import unittest
from pathlib import Path

from voicebot.final_call_selection import (
    discover_call_dirs,
    evaluate_call_dir,
    render_markdown_report,
    select_top_candidates,
)


class FinalCallSelectionTests(unittest.TestCase):
    def test_discovers_grouped_calls_before_legacy_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            calls_root = Path(temp_dir) / "calls"
            grouped = calls_root / "smoke" / "call-001"
            legacy = calls_root / "call-001"
            grouped.mkdir(parents=True)
            legacy.mkdir(parents=True)

            self.assertEqual(discover_call_dirs(calls_root), [grouped])
            self.assertEqual(discover_call_dirs(calls_root, include_legacy=True), [grouped, legacy])

    def test_hard_gate_requires_at_least_sixty_seconds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "smoke" / "call-001",
                duration=59,
                turns=[
                    ("PGAI Agent", "How may I help you today?"),
                    ("Patient Bot", "I need an appointment."),
                    ("PGAI Agent", "Can I have your date of birth?"),
                    ("Patient Bot", "March 14, 1987."),
                    ("PGAI Agent", "What time works?"),
                    ("Patient Bot", "Morning next week."),
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        self.assertFalse(candidate.gates_passed)
        self.assertIn("duration_below_60s", candidate.gate_failures)
        self.assertEqual(candidate.score, 0.0)

    def test_scores_longer_balanced_calls_as_review_candidates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "calls" / "smoke"
            short_call = self._write_call(
                root / "call-001",
                duration=70,
                turns=self._turns(4),
            )
            long_call = self._write_call(
                root / "call-002",
                duration=150,
                turns=self._turns(12),
            )

            candidates = [evaluate_call_dir(short_call), evaluate_call_dir(long_call)]
            selected = select_top_candidates(candidates, top_n=1)

        self.assertEqual(selected[0].call_id, "smoke-call-002")
        self.assertGreater(selected[0].score, candidates[0].score)

    def test_patient_meta_disclosure_fails_sensibility(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "smoke" / "call-001",
                duration=120,
                turns=[
                    ("PGAI Agent", "How may I help you today?"),
                    ("Patient Bot", "This is a test harness call."),
                    ("PGAI Agent", "Can you repeat that?"),
                    ("Patient Bot", "I need an appointment."),
                    ("PGAI Agent", "What time works?"),
                    ("Patient Bot", "Morning next week."),
                ],
            )

            candidate = evaluate_call_dir(call_dir)
            selected = select_top_candidates([candidate])

        self.assertEqual(candidate.sensibility_status, "fail")
        self.assertEqual(selected, [])

    def test_automated_first_pass_ignores_transcription_error_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "smoke" / "call-001",
                duration=120,
                turns=[
                    ("PGAI Agent", "Am I speaking with James? Para espaÃ±ol, press two."),
                    ("Patient Bot", "I think you have the wrong patient. The caller is Maya."),
                    ("PGAI Agent", "Would you like to use your phone number?"),
                    ("PGAI Agent", "You have on file with us."),
                    ("PGAI Agent", "그렇구나."),
                    ("Patient Bot", "That phone number is not mine."),
                    ("PGAI Agent", "I'll transfer you to a representative. Please wait."),
                    ("PGAI Agent", "Hello, you've reached the Pretty Good AI test line. Goodbye."),
                    ("Patient Bot", "Okay."),
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        categories = {finding.category for finding in candidate.issue_findings}
        self.assertIn("factual", categories)
        self.assertIn("flow", categories)
        self.assertNotIn("voice_quality", categories)
        summaries = {finding.summary for finding in candidate.issue_findings}
        self.assertNotIn("Agent utterance may be clipped or missing context.", summaries)
        self.assertIn(
            "Agent escalated or transferred the call instead of resolving it in-bot.",
            summaries,
        )

    def test_dead_escalation_line_alone_is_not_a_flow_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "smoke" / "call-001",
                duration=120,
                turns=[
                    ("PGAI Agent", "How may I help you today?"),
                    ("Patient Bot", "I need an appointment."),
                    ("PGAI Agent", "Can I have your date of birth?"),
                    ("Patient Bot", "March 14, 1987."),
                    ("PGAI Agent", "Hello, you've reached the Pretty Good AI test line. Goodbye."),
                    ("Patient Bot", "Goodbye."),
                    ("PGAI Agent", "Thank you for calling."),
                    ("Patient Bot", "Thanks."),
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        summaries = {finding.summary for finding in candidate.issue_findings}
        self.assertNotIn(
            "Agent escalated or transferred the call instead of resolving it in-bot.",
            summaries,
        )
        self.assertNotIn(
            "Transfer path appears to end at the test line instead of a meaningful resolution.",
            summaries,
        )

    def test_markdown_report_mentions_manual_review_and_hard_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "smoke" / "call-001",
                duration=120,
                turns=self._turns(8),
            )
            candidate = evaluate_call_dir(call_dir)
            selected = select_top_candidates([candidate])

            report = render_markdown_report([candidate], selected)

        self.assertIn("HARD GATE", report)
        self.assertIn("Manual Review Checklist", report)
        self.assertIn("Ranking does not reward success", report)

    def _write_call(
        self,
        call_dir: Path,
        *,
        duration: int,
        turns: list[tuple[str, str]],
    ) -> Path:
        call_dir.mkdir(parents=True)
        (call_dir / "recording.mp3").write_bytes(b"fake audio")
        (call_dir / "recording_metadata.json").write_text(
            json.dumps({"duration": str(duration)}) + "\n",
            encoding="utf-8",
        )
        (call_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "call_id": f"{call_dir.parent.name}-{call_dir.name}",
                    "call_type": call_dir.parent.name,
                    "scenario_id": "T-01-smoke",
                    "runtime_scenario_id": "t01_smoke",
                    "patient_profile": "maya_patel",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        transcript = "\n".join(f"{speaker}: {text}" for speaker, text in turns) + "\n"
        (call_dir / "transcript.txt").write_text(transcript, encoding="utf-8")
        return call_dir

    def _turns(self, pairs: int) -> list[tuple[str, str]]:
        turns: list[tuple[str, str]] = []
        for index in range(pairs):
            turns.append(("PGAI Agent", f"Agent question number {index}?"))
            turns.append(("Patient Bot", f"Patient answer number {index}."))
        return turns


if __name__ == "__main__":
    unittest.main()
