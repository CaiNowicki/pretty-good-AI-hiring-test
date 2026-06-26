import json
import tempfile
import unittest
from pathlib import Path

from voicebot.final_call_selection import (
    CallCandidate,
    IssueFinding,
    TurnTakingMetrics,
    _issue_opportunity_bonus,
    discover_call_dirs,
    evaluate_calls,
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

    def test_evaluate_calls_excludes_directories_without_transcripts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "calls" / "smoke"
            missing_transcript = root / "call-001"
            missing_transcript.mkdir(parents=True)
            self._write_call(root / "call-002", duration=120, turns=self._turns(4))

            candidates = evaluate_calls(Path(temp_dir) / "calls")

        self.assertEqual([candidate.call_id for candidate in candidates], ["smoke-call-002"])

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

    def test_dead_escalation_line_does_not_change_end_call_score(self):
        common_turns = [
            ("PGAI Agent", "How may I help you today?"),
            ("Patient Bot", "I need an appointment."),
            ("PGAI Agent", "Can I have your date of birth?"),
            ("Patient Bot", "March 14, 1987."),
            ("PGAI Agent", "I can't proceed further right now, so please wait."),
            ("Patient Bot", "Okay."),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "calls" / "smoke"
            with_dead_line = self._write_call(
                root / "call-001",
                duration=120,
                turns=[
                    *common_turns,
                    ("PGAI Agent", "Hello, you've reached the Pretty Good AI test line. Goodbye."),
                    ("Patient Bot", "Goodbye."),
                ],
            )
            without_dead_line = self._write_call(
                root / "call-002",
                duration=120,
                turns=[
                    *common_turns,
                    ("PGAI Agent", "Hello, patient support is ready on this line now. Goodbye."),
                    ("Patient Bot", "Goodbye."),
                ],
            )

            dead_line_candidate = evaluate_call_dir(with_dead_line)
            neutral_candidate = evaluate_call_dir(without_dead_line)

        dead_line_summaries = {
            finding.summary for finding in dead_line_candidate.issue_findings
        }
        neutral_summaries = {
            finding.summary for finding in neutral_candidate.issue_findings
        }
        self.assertEqual(dead_line_summaries, neutral_summaries)
        self.assertEqual(dead_line_candidate.score, neutral_candidate.score)

    def test_records_handoff_is_not_scored_as_unwarranted_escalation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "orthopedic_edge_cases" / "call-001",
                duration=120,
                scenario_text=(
                    "id: E-05-records-request\n"
                    "success_criteria: Agent handles a records request, explains "
                    "authorization, and gives a realistic transfer timeline.\n"
                ),
                turns=[
                    ("PGAI Agent", "How may I help you today?"),
                    ("Patient Bot", "I need my records sent to another doctor."),
                    ("PGAI Agent", "Medical records can route that request after authorization."),
                    ("Patient Bot", "Okay, how do I do that?"),
                    ("PGAI Agent", "Please wait while I transfer you to the records team."),
                    ("Patient Bot", "Thanks."),
                    ("PGAI Agent", "Hello, you've reached the Pretty Good AI test line. Goodbye."),
                    ("Patient Bot", "Goodbye."),
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        summaries = {finding.summary for finding in candidate.issue_findings}
        self.assertNotIn(
            "Agent escalated or transferred the call instead of resolving it in-bot.",
            summaries,
        )

    def test_standard_refill_support_team_submission_is_not_unwarranted_escalation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "medication_refill" / "call-001",
                duration=120,
                scenario_text=(
                    "id: M-01-standard-refill\n"
                    "goal: Request a refill for lisinopril.\n"
                    "success_criteria: Agent confirms the refill request is submitted "
                    "and gives next steps.\n"
                ),
                turns=[
                    ("PGAI Agent", "How may I help you today?"),
                    ("Patient Bot", "I need a medication refill."),
                    ("PGAI Agent", "Which medication do you need refilled?"),
                    ("Patient Bot", "Lisinopril 10mg."),
                    ("PGAI Agent", "I've documented your medication refill request and sent it to our clinic support team."),
                    ("Patient Bot", "Thank you."),
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        summaries = {finding.summary for finding in candidate.issue_findings}
        self.assertNotIn(
            "Agent escalated or transferred the call instead of resolving it in-bot.",
            summaries,
        )

    def test_conversation_artifacts_do_not_add_bug_opportunity_bonus(self):
        self.assertEqual(
            _issue_opportunity_bonus(
                [
                    IssueFinding(
                        "flow",
                        "medium",
                        "conversation",
                        "Long same-speaker run may indicate interruption.",
                        "Longest same-speaker run: 5",
                    )
                ]
            ),
            0.0,
        )

    def test_high_confidence_agent_bugs_strongly_influence_score(self):
        high_agent_bug_bonus = _issue_opportunity_bonus(
            [
                IssueFinding(
                    "factual",
                    "high",
                    "agent_bot",
                    "Agent may have assumed or surfaced the wrong patient identity.",
                    "Am I speaking with James?",
                )
            ]
        )
        medium_agent_bug_bonus = _issue_opportunity_bonus(
            [
                IssueFinding(
                    "flow",
                    "medium",
                    "agent_bot",
                    "Agent escalated or transferred the call instead of resolving it in-bot.",
                    "Please wait while I transfer you.",
                )
            ]
        )

        self.assertGreaterEqual(high_agent_bug_bonus, 10.0)
        self.assertGreater(high_agent_bug_bonus, medium_agent_bug_bonus)

    def test_patient_role_drift_penalizes_candidate_score(self):
        common_agent_turns = [
            ("PGAI Agent", "How may I help you today?"),
            ("Patient Bot", "I need an appointment."),
            ("PGAI Agent", "Can I have your date of birth?"),
            ("Patient Bot", "March 14, 1987."),
            ("PGAI Agent", "What time works?"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "calls" / "smoke"
            clean_call = self._write_call(
                root / "call-001",
                duration=120,
                turns=[
                    *common_agent_turns,
                    ("Patient Bot", "Morning next week."),
                ],
            )
            drift_call = self._write_call(
                root / "call-002",
                duration=120,
                turns=[
                    *common_agent_turns,
                    ("Patient Bot", "I'll book that appointment for you."),
                ],
            )

            clean_candidate = evaluate_call_dir(clean_call)
            drift_candidate = evaluate_call_dir(drift_call)

        self.assertIn("patient_role_drift_phrase", drift_candidate.sensibility_flags)
        self.assertLess(drift_candidate.score, clean_candidate.score)

    def test_repeated_verification_exchanges_use_verification_loop_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "appointment_scheduling" / "call-001",
                duration=120,
                turns=[
                    ("PGAI Agent", "Please provide your date of birth."),
                    ("Patient Bot", "My date of birth is July 22, 1980."),
                    ("PGAI Agent", "Please provide your date of birth."),
                    ("Patient Bot", "My date of birth is July 22, 1980."),
                    ("PGAI Agent", "Please provide the full phone number you have on file."),
                    ("Patient Bot", "555-318-4492"),
                    ("PGAI Agent", "Please provide the full phone number you have on file."),
                    ("Patient Bot", "555-318-4492"),
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        self.assertIn("possible_verification_loop_4", candidate.sensibility_flags)
        self.assertFalse(
            any(flag.startswith("repeated_utterance_count_") for flag in candidate.sensibility_flags)
        )

    def test_already_provided_pushback_flags_and_boosts_selection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "appointment_scheduling" / "call-001",
                duration=120,
                turns=[
                    ("PGAI Agent", "Please provide your date of birth."),
                    ("Patient Bot", "My date of birth is July 22, 1980."),
                    ("PGAI Agent", "Please provide your date of birth."),
                    ("Patient Bot", "I already gave you my date of birth. It is July 22, 1980."),
                    ("PGAI Agent", "Please provide your phone number."),
                    ("Patient Bot", "555-318-4492."),
                    ("PGAI Agent", "Please provide your phone number."),
                    ("Patient Bot", "I already told you my phone number. It is 555-318-4492."),
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        self.assertTrue(
            any(
                flag.startswith("possible_verification_loop_")
                for flag in candidate.sensibility_flags
            )
        )
        summaries = {finding.summary for finding in candidate.issue_findings}
        self.assertIn(
            "Patient repeatedly indicates the agent is re-asking for already-provided verification.",
            summaries,
        )

        pushback_finding = IssueFinding(
            "flow",
            "medium",
            "conversation",
            "Patient repeatedly indicates the agent is re-asking for already-provided verification.",
            "I already gave you my date of birth.",
        )
        selected = select_top_candidates(
            [
                self._candidate("plain-call", 90.0, []),
                self._candidate("pushback-call", 89.0, [pushback_finding]),
            ],
            top_n=1,
            max_per_call_type=10,
        )

        self.assertEqual(selected[0].call_id, "pushback-call")

    def test_selection_prioritizes_novel_agent_bug_signatures(self):
        duplicate_bug = IssueFinding(
            "factual",
            "high",
            "agent_bot",
            "Agent may have assumed or surfaced the wrong patient identity.",
            "Am I speaking with James?",
        )
        novel_bug = IssueFinding(
            "factual",
            "high",
            "agent_bot",
            "Agent may have confirmed an incorrect phone number or stale record.",
            "That phone number is not mine.",
        )
        selected = select_top_candidates(
            [
                self._candidate("duplicate-stronger", 100.0, [duplicate_bug]),
                self._candidate("duplicate-slightly-weaker", 99.0, [duplicate_bug]),
                self._candidate("novel-bug", 92.0, [novel_bug]),
            ],
            top_n=2,
            max_per_call_type=10,
        )

        self.assertEqual(
            [candidate.call_id for candidate in selected],
            ["duplicate-stronger", "novel-bug"],
        )

    def test_clean_turn_taking_adds_small_selection_bonus(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "smoke" / "call-001",
                duration=120,
                turns=self._turns(4),
            )
            self._write_events(
                call_dir,
                [
                    {"event": "openai", "payload": {"type": "input_audio_buffer.speech_started"}},
                    {"event": "openai", "payload": {"type": "input_audio_buffer.speech_stopped"}},
                    {
                        "event": "openai",
                        "payload": {"type": "response.output_audio_transcript.done"},
                    },
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        self.assertEqual(candidate.turn_taking.score_adjustment, 4.0)
        self.assertEqual(candidate.turn_taking.agent_over_patient_count, 0)
        self.assertEqual(candidate.turn_taking.patient_over_agent_count, 0)

    def test_patient_over_agent_timing_penalty_is_larger_than_agent_over_patient(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "calls" / "smoke"
            clean_call = self._write_call(root / "call-001", duration=120, turns=self._turns(4))
            agent_overlap_call = self._write_call(root / "call-002", duration=120, turns=self._turns(4))
            patient_overlap_call = self._write_call(root / "call-003", duration=120, turns=self._turns(4))
            self._write_events(
                clean_call,
                [
                    {"event": "openai", "payload": {"type": "input_audio_buffer.speech_started"}},
                    {"event": "openai", "payload": {"type": "input_audio_buffer.speech_stopped"}},
                    {
                        "event": "openai",
                        "payload": {
                            "type": "response.output_audio_transcript.delta",
                            "response_id": "response-clean",
                        },
                    },
                    {
                        "event": "openai",
                        "payload": {
                            "type": "response.output_audio_transcript.done",
                            "response_id": "response-clean",
                        },
                    },
                ],
            )
            self._write_events(
                agent_overlap_call,
                [
                    {
                        "event": "openai",
                        "payload": {
                            "type": "response.output_audio_transcript.delta",
                            "response_id": "response-agent-overlap",
                        },
                    },
                    {"event": "openai", "payload": {"type": "input_audio_buffer.speech_started"}},
                    {
                        "event": "openai",
                        "payload": {
                            "type": "response.output_audio_transcript.done",
                            "response_id": "response-agent-overlap",
                        },
                    },
                ],
            )
            self._write_events(
                patient_overlap_call,
                [
                    {"event": "openai", "payload": {"type": "input_audio_buffer.speech_started"}},
                    {
                        "event": "openai",
                        "payload": {
                            "type": "response.output_audio_transcript.delta",
                            "response_id": "response-patient-overlap",
                        },
                    },
                    {"event": "openai", "payload": {"type": "input_audio_buffer.speech_stopped"}},
                ],
            )

            clean_candidate = evaluate_call_dir(clean_call)
            agent_overlap_candidate = evaluate_call_dir(agent_overlap_call)
            patient_overlap_candidate = evaluate_call_dir(patient_overlap_call)

        agent_penalty = clean_candidate.score - agent_overlap_candidate.score
        patient_penalty = clean_candidate.score - patient_overlap_candidate.score
        self.assertGreater(patient_penalty, agent_penalty)
        self.assertEqual(agent_overlap_candidate.turn_taking.agent_over_patient_count, 1)
        self.assertEqual(patient_overlap_candidate.turn_taking.patient_over_agent_count, 1)

    def test_held_patient_response_is_not_counted_as_talkover(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "smoke" / "call-001",
                duration=120,
                turns=self._turns(4),
            )
            self._write_events(
                call_dir,
                [
                    {"event": "openai", "payload": {"type": "input_audio_buffer.speech_started"}},
                    {
                        "event": "patient_response.held",
                        "reason": "agent_speech_in_progress",
                    },
                    {"event": "openai", "payload": {"type": "input_audio_buffer.speech_stopped"}},
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        self.assertEqual(candidate.turn_taking.agent_over_patient_count, 0)
        self.assertEqual(candidate.turn_taking.patient_over_agent_count, 0)
        self.assertEqual(candidate.turn_taking.score_adjustment, 4.0)

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

    def test_markdown_combines_review_flags_with_selected_findings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "appointment_scheduling" / "call-001",
                duration=120,
                turns=[
                    ("PGAI Agent", "Please provide your date of birth."),
                    ("Patient Bot", "My date of birth is July 22, 1980."),
                    ("PGAI Agent", "Please provide your date of birth."),
                    ("Patient Bot", "My date of birth is July 22, 1980."),
                    ("PGAI Agent", "Please provide your phone number."),
                    ("Patient Bot", "555-318-4492"),
                    ("PGAI Agent", "Please provide your phone number."),
                    ("Patient Bot", "555-318-4492"),
                ],
            )
            candidate = evaluate_call_dir(call_dir)
            selected = select_top_candidates([candidate])

            report = render_markdown_report([candidate], selected)

        self.assertIn("## Automated Issues In Selected Calls", report)
        self.assertIn("| Type of Error | Selected Calls |", report)
        self.assertIn("## Selected Call Findings", report)
        self.assertIn("Possible verification loop detected from repeated verification exchanges.", report)
        self.assertIn(
            "PGAI Agent repeated 2 times: Please provide your date of birth.",
            report,
        )
        self.assertIn(
            "Patient Bot repeated 2 times: My date of birth is July 22, 1980.",
            report,
        )
        self.assertNotIn(
            "| review_flag | medium | conversation | "
            "Possible verification loop detected from repeated verification exchanges. | "
            "possible_verification_loop_4 |",
            report,
        )
        self.assertNotIn("## Selected Calls With Review Flags", report)

    def test_missing_agent_action_evidence_uses_formal_absence_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            call_dir = self._write_call(
                Path(temp_dir) / "calls" / "orthopedic_edge_cases" / "call-001",
                duration=120,
                scenario_text=(
                    "id: E-04-minor-without-parent\n"
                    "patient_profile: minor_athlete\n"
                    "success_criteria: Agent acknowledges minor consent requirements.\n"
                ),
                turns=[
                    ("PGAI Agent", "This call may be recorded for quality and training purposes. Para español, oprima el dos."),
                    ("PGAI Agent", "How can I help you today?"),
                    ("Patient Bot", "I need an appointment."),
                    ("PGAI Agent", "What is your date of birth?"),
                    ("Patient Bot", "May 1, 2010."),
                    ("PGAI Agent", "What time works?"),
                ],
            )

            candidate = evaluate_call_dir(call_dir)

        evidence = {
            finding.evidence
            for finding in candidate.issue_findings
            if finding.summary == "Minor or guardian context may not have been acknowledged by the agent."
        }
        self.assertEqual(
            evidence,
            {
                "No direct transcript line: this issue is inferred from minor or guardian context and the absence of agent acknowledgement."
            },
        )

    def _write_call(
        self,
        call_dir: Path,
        *,
        duration: int,
        turns: list[tuple[str, str]],
        scenario_text: str = "",
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
        if scenario_text:
            (call_dir / "scenario.yaml").write_text(scenario_text, encoding="utf-8")
        return call_dir

    def _write_events(self, call_dir: Path, events: list[dict[str, object]]) -> None:
        lines = []
        for index, event in enumerate(events, start=1):
            payload = {"time": f"2026-06-26T00:00:{index:02d}+00:00", **event}
            lines.append(json.dumps(payload))
        (call_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _turns(self, pairs: int) -> list[tuple[str, str]]:
        turns: list[tuple[str, str]] = []
        for index in range(pairs):
            turns.append(("PGAI Agent", f"Agent question number {index}?"))
            turns.append(("Patient Bot", f"Patient answer number {index}."))
        return turns

    def _candidate(
        self,
        call_id: str,
        score: float,
        findings: list[IssueFinding],
    ) -> CallCandidate:
        return CallCandidate(
            call_id=call_id,
            call_type="smoke",
            call_dir=f"/tmp/{call_id}",
            scenario_id="T-01-smoke",
            runtime_scenario_id="t01_smoke",
            patient_profile="maya_patel",
            duration_seconds=120.0,
            duration_source="recording_metadata.json",
            transcript_turns=12,
            agent_turns=6,
            patient_turns=6,
            transcript_words=120,
            recording_path=f"/tmp/{call_id}/recording.mp3",
            transcript_path=f"/tmp/{call_id}/transcript.txt",
            gates_passed=True,
            gate_failures=[],
            sensibility_status="pass",
            sensibility_flags=[],
            issue_findings=findings,
            turn_taking=TurnTakingMetrics(False, 0, 0, 0, 0.0),
            score=score,
        )


if __name__ == "__main__":
    unittest.main()
