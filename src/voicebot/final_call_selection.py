"""Rank completed call artifacts for final-package review."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from voicebot.artifacts import DEFAULT_ARTIFACTS_ROOT, DEFAULT_CALLS_ROOT, utc_now_iso


DEFAULT_OUTPUT_DIR = DEFAULT_ARTIFACTS_ROOT / "final_call_selection"
SPEAKER_PATTERN = re.compile(r"^(PGAI Agent|Patient Bot):\s*(.*)$")
CALL_DIR_PATTERN = re.compile(r"^call-\d+$")
META_DISCLOSURE_PATTERN = re.compile(
    r"\b(test harness|this is a test|i am (?:an )?(?:ai|bot|assistant)|automated caller)\b",
    re.IGNORECASE,
)
PATIENT_ROLE_DRIFT_PATTERN = re.compile(
    r"\b("
    r"let me check|i can check|i can schedule|i'?ll book|i'?ll put you down|"
    r"i created the appointment|i'?ve changed that|i'?ll adjust|you'?re all set"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TranscriptTurn:
    speaker: str
    text: str


@dataclass(frozen=True)
class IssueFinding:
    category: str
    severity: str
    source_guess: str
    summary: str
    evidence: str


@dataclass(frozen=True)
class TurnTakingMetrics:
    events_observed: bool
    agent_over_patient_count: int
    patient_over_agent_count: int
    patient_response_cancelled_count: int
    score_adjustment: float


@dataclass(frozen=True)
class CallCandidate:
    call_id: str
    call_type: str
    call_dir: str
    scenario_id: str | None
    runtime_scenario_id: str | None
    patient_profile: str | None
    duration_seconds: float | None
    duration_source: str | None
    transcript_turns: int
    agent_turns: int
    patient_turns: int
    transcript_words: int
    recording_path: str | None
    transcript_path: str | None
    gates_passed: bool
    gate_failures: list[str]
    sensibility_status: str
    sensibility_flags: list[str]
    issue_findings: list[IssueFinding]
    turn_taking: TurnTakingMetrics
    score: float
    rank: int | None = None


def discover_call_dirs(calls_root: Path, *, include_legacy: bool = False) -> list[Path]:
    """Find call artifact directories, preferring grouped final-call artifacts."""
    if not calls_root.exists():
        return []

    grouped: list[Path] = []
    legacy: list[Path] = []
    for child in sorted(calls_root.iterdir()):
        if not child.is_dir():
            continue
        if CALL_DIR_PATTERN.match(child.name):
            legacy.append(child)
            continue
        grouped.extend(sorted(path for path in child.glob("call-*") if path.is_dir()))

    if include_legacy:
        return [*grouped, *legacy]
    return grouped


def evaluate_call_dir(call_dir: Path, *, min_duration_seconds: float = 60.0) -> CallCandidate:
    metadata = _read_json(call_dir / "metadata.json")
    transcript_path = call_dir / "transcript.txt"
    recording_path = _find_recording(call_dir)
    turns = _read_transcript_turns(transcript_path)
    duration_seconds, duration_source = _duration_seconds(call_dir, metadata)

    call_type = _call_type(call_dir, metadata)
    call_id = _metadata_text(metadata, "call_id") or f"{call_type}-{call_dir.name}"
    scenario_id = _metadata_text(metadata, "scenario_id")
    runtime_scenario_id = _metadata_text(metadata, "runtime_scenario_id")
    patient_profile = _metadata_text(metadata, "patient_profile")

    gate_failures = _gate_failures(
        call_dir,
        duration_seconds=duration_seconds,
        min_duration_seconds=min_duration_seconds,
        recording_path=recording_path,
        transcript_path=transcript_path,
        turns=turns,
    )
    sensibility_status, sensibility_flags = _sensibility_check(turns)
    turn_taking = _turn_taking_metrics(call_dir, turns)
    issue_findings = _automated_issue_scan(
        call_dir,
        metadata,
        turns,
        duration_seconds=duration_seconds,
        gate_failures=gate_failures,
    )
    score = _score_candidate(
        duration_seconds=duration_seconds,
        turns=turns,
        sensibility_status=sensibility_status,
        sensibility_flags=sensibility_flags,
        gate_failures=gate_failures,
        issue_findings=issue_findings,
        turn_taking=turn_taking,
    )

    agent_turns = sum(1 for turn in turns if turn.speaker == "PGAI Agent")
    patient_turns = sum(1 for turn in turns if turn.speaker == "Patient Bot")
    transcript_words = sum(len(turn.text.split()) for turn in turns)
    return CallCandidate(
        call_id=call_id,
        call_type=call_type,
        call_dir=str(call_dir),
        scenario_id=scenario_id,
        runtime_scenario_id=runtime_scenario_id,
        patient_profile=patient_profile,
        duration_seconds=duration_seconds,
        duration_source=duration_source,
        transcript_turns=len(turns),
        agent_turns=agent_turns,
        patient_turns=patient_turns,
        transcript_words=transcript_words,
        recording_path=str(recording_path) if recording_path else None,
        transcript_path=str(transcript_path) if transcript_path.exists() else None,
        gates_passed=not gate_failures,
        gate_failures=gate_failures,
        sensibility_status=sensibility_status,
        sensibility_flags=sensibility_flags,
        issue_findings=issue_findings,
        turn_taking=turn_taking,
        score=score,
    )


def evaluate_calls(
    calls_root: Path = DEFAULT_CALLS_ROOT,
    *,
    include_legacy: bool = False,
    min_duration_seconds: float = 60.0,
) -> list[CallCandidate]:
    return [
        evaluate_call_dir(call_dir, min_duration_seconds=min_duration_seconds)
        for call_dir in discover_call_dirs(calls_root, include_legacy=include_legacy)
        if (call_dir / "transcript.txt").exists()
    ]


def select_top_candidates(
    candidates: Iterable[CallCandidate],
    *,
    top_n: int = 10,
    max_per_call_type: int = 3,
) -> list[CallCandidate]:
    eligible = [
        candidate
        for candidate in candidates
        if candidate.gates_passed and candidate.sensibility_status != "fail"
    ]
    eligible.sort(key=lambda candidate: (-candidate.score, candidate.call_type, candidate.call_id))

    selected: list[CallCandidate] = []
    remaining = list(eligible)
    type_counts: dict[str, int] = {}
    seen_issue_signatures: set[tuple[str, str]] = set()
    issue_signature_counts = _issue_signature_counts(eligible)
    while len(selected) < top_n:
        candidate = _pop_next_selection_candidate(
            remaining,
            seen_issue_signatures=seen_issue_signatures,
            issue_signature_counts=issue_signature_counts,
            type_counts=type_counts,
            max_per_call_type=max_per_call_type,
        )
        if candidate is None:
            break
        selected.append(candidate)
        type_counts[candidate.call_type] = type_counts.get(candidate.call_type, 0) + 1
        seen_issue_signatures.update(_agent_bug_issue_signatures(candidate.issue_findings))

    while len(selected) < top_n:
        candidate = _pop_next_selection_candidate(
            remaining,
            seen_issue_signatures=seen_issue_signatures,
            issue_signature_counts=issue_signature_counts,
            type_counts=type_counts,
            max_per_call_type=None,
        )
        if candidate is None:
            break
        selected.append(candidate)
        type_counts[candidate.call_type] = type_counts.get(candidate.call_type, 0) + 1
        seen_issue_signatures.update(_agent_bug_issue_signatures(candidate.issue_findings))

    return [replace(candidate, rank=index) for index, candidate in enumerate(selected, start=1)]


def _pop_next_selection_candidate(
    candidates: list[CallCandidate],
    *,
    seen_issue_signatures: set[tuple[str, str]],
    issue_signature_counts: dict[tuple[str, str], int],
    type_counts: dict[str, int],
    max_per_call_type: int | None,
) -> CallCandidate | None:
    best_index: int | None = None
    best_key: tuple[float, float, int] | None = None
    for index, candidate in enumerate(candidates):
        if (
            max_per_call_type is not None
            and type_counts.get(candidate.call_type, 0) >= max_per_call_type
        ):
            continue
        novelty_bonus = _selection_novelty_bonus(
            candidate,
            seen_issue_signatures=seen_issue_signatures,
            issue_signature_counts=issue_signature_counts,
        )
        key = (candidate.score + novelty_bonus, candidate.score, -index)
        if best_key is None or key > best_key:
            best_key = key
            best_index = index
    if best_index is None:
        return None
    return candidates.pop(best_index)


def _selection_novelty_bonus(
    candidate: CallCandidate,
    *,
    seen_issue_signatures: set[tuple[str, str]],
    issue_signature_counts: dict[tuple[str, str], int],
) -> float:
    bonus = 0.0
    for finding in candidate.issue_findings:
        signature = _agent_bug_issue_signature(finding)
        if signature is None or signature in seen_issue_signatures:
            continue
        bonus += _finding_bug_value(finding)
        frequency = issue_signature_counts.get(signature, 0)
        if frequency == 1:
            bonus += 4.0
        elif frequency == 2:
            bonus += 2.0
    return min(bonus, 12.0)


def _issue_signature_counts(candidates: Iterable[CallCandidate]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        for signature in set(_agent_bug_issue_signatures(candidate.issue_findings)):
            counts[signature] = counts.get(signature, 0) + 1
    return counts


def _agent_bug_issue_signatures(findings: Iterable[IssueFinding]) -> list[tuple[str, str]]:
    signatures: list[tuple[str, str]] = []
    for finding in findings:
        signature = _agent_bug_issue_signature(finding)
        if signature is not None:
            signatures.append(signature)
    return signatures


def _agent_bug_issue_signature(finding: IssueFinding) -> tuple[str, str] | None:
    if finding.source_guess not in {"agent_bot", "conversation", "unknown"}:
        return None
    if finding.source_guess == "conversation" and finding.summary != (
        "Patient repeatedly indicates the agent is re-asking for already-provided verification."
    ):
        return None
    if finding.severity == "low":
        return None
    return (finding.category, finding.summary)


def _finding_bug_value(finding: IssueFinding) -> float:
    if finding.severity == "high":
        value = 8.0
    elif finding.severity == "medium":
        value = 4.0
    else:
        value = 1.0
    if finding.source_guess == "unknown":
        value *= 0.5
    return value


def write_selection_reports(
    candidates: list[CallCandidate],
    selected: list[CallCandidate],
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    min_duration_seconds: float = 60.0,
    top_n: int = 10,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": utc_now_iso(),
        "selection_policy": {
            "top_n": top_n,
            "min_duration_seconds": min_duration_seconds,
            "hard_gate": f"duration_seconds >= {min_duration_seconds:g}",
            "intent": (
                "Rank calls for judging bot behavior, not for making either bot look good."
            ),
            "manual_review_required": True,
            "automated_first_pass": [
                "policy",
                "factual",
                "flow",
                "voice_quality",
            ],
        },
        "selected": [asdict(candidate) for candidate in selected],
        "all_candidates": [asdict(candidate) for candidate in candidates],
    }
    json_path = output_dir / "final_call_candidates.json"
    md_path = output_dir / "final_call_candidates.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(
        render_markdown_report(
            candidates,
            selected,
            min_duration_seconds=min_duration_seconds,
            top_n=top_n,
        ),
        encoding="utf-8",
    )
    return json_path, md_path


def render_markdown_report(
    candidates: list[CallCandidate],
    selected: list[CallCandidate],
    *,
    min_duration_seconds: float = 60.0,
    top_n: int = 10,
) -> str:
    eligible = [
        candidate
        for candidate in candidates
        if candidate.gates_passed and candidate.sensibility_status != "fail"
    ]
    rejected = [candidate for candidate in candidates if not candidate.gates_passed]
    issue_counts = _issue_counts(candidates)
    lines = [
        "# Final Call Candidate Review",
        "",
        f"Generated: {_friendly_now()}",
        "",
        "Selection policy:",
        (
            f"- HARD GATE: calls must be at least {min_duration_seconds:g} seconds long, "
            "with a non-empty recording and speaker-labeled transcript."
        ),
        "- Ranking favors judgeability: longer calls, more turns, speaker balance, and transcript coherence.",
        "- Ranking does not reward success, failure, or whether either bot looks good.",
        "- Automated first pass flags policy, factual, flow, and voice-quality issues for reviewer triage.",
        "- Manual listening/review is still required before a call is included in the final package.",
        "",
        f"Discovered calls: {len(candidates)}",
        f"Eligible after hard gates and severe sensibility checks: {len(eligible)}",
        f"Rejected by hard gate: {len(rejected)}",
        "",
        "## Automated First Pass",
        "",
        _issue_count_line(issue_counts),
        "",
        f"## Top {top_n} Review Queue",
        "",
    ]
    if not selected:
        lines.append("No calls passed the gates yet.")
    else:
        lines.extend(_candidate_table(selected, include_rank=True))

    lines.extend(
        [
            "",
            "## Manual Review Checklist",
            "",
            "- Listen to the recording and confirm the transcript matches both speakers.",
            "- Check every automated issue flag against the recording before promoting it.",
            "- Confirm the dialogue stays sensible through the end, not just near the bug evidence.",
            "- Exclude calls where patient-bot glitches create the apparent issue.",
            "- Exclude calls where the agent-bot outcome is unjudgeable because the call setup degraded.",
            "- Prefer calls that expose decision points, recovery behavior, clarifications, or safety handling.",
            "",
        ]
    )
    selected_findings = _selected_automated_findings(selected)
    if selected_findings:
        lines.extend(["## Automated Issues In Selected Calls", ""])
        lines.extend(_selected_issue_count_table(selected_findings))
        lines.append("")
        lines.extend(["## Selected Call Findings", ""])
        lines.extend(_selected_findings_table(selected_findings))
        lines.append("")

    near_misses = sorted(
        [
            candidate
            for candidate in eligible
            if candidate.call_dir not in {selected_call.call_dir for selected_call in selected}
        ],
        key=lambda candidate: (-candidate.score, candidate.call_type, candidate.call_id),
    )[:10]
    if near_misses:
        lines.extend(["## Near Misses", ""])
        lines.extend(_candidate_table(near_misses, include_rank=False))
        lines.append("")

    if rejected:
        lines.extend(["## Hard-Gate Rejections", ""])
        lines.extend(_rejection_lines(rejected[:50]))
        if len(rejected) > 50:
            lines.append(f"- ... {len(rejected) - 50} more rejected calls omitted.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run_selection_pipeline(args: argparse.Namespace) -> int:
    candidates = evaluate_calls(
        Path(args.calls_root),
        include_legacy=args.include_legacy,
        min_duration_seconds=args.min_duration_seconds,
    )
    selected = select_top_candidates(
        candidates,
        top_n=args.top_n,
        max_per_call_type=args.max_per_call_type,
    )
    json_path, md_path = write_selection_reports(
        candidates,
        selected,
        Path(args.output_dir),
        min_duration_seconds=args.min_duration_seconds,
        top_n=args.top_n,
    )
    print(f"Wrote JSON report: {json_path}")
    print(f"Wrote review report: {md_path}")
    print(f"Selected {len(selected)} of {len(candidates)} discovered calls for review.")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank completed call artifacts for final-package review."
    )
    parser.add_argument("--calls-root", default=str(DEFAULT_CALLS_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-duration-seconds", type=float, default=60.0)
    parser.add_argument(
        "--max-per-call-type",
        type=int,
        default=3,
        help="Diversity cap before backfilling remaining slots.",
    )
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="Also consider older flat artifacts/calls/call-### calibration folders.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    return run_selection_pipeline(parser.parse_args(argv))


def _candidate_table(candidates: list[CallCandidate], *, include_rank: bool) -> list[str]:
    rank_header = "| Rank " if include_rank else ""
    rank_separator = "| --- " if include_rank else ""
    lines = [
        (
            f"{rank_header}| Call | Type | Duration | Turns | Score | "
            "Review | Issues | Flags |"
        ),
        f"{rank_separator}| --- | --- | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for candidate in candidates:
        rank_cell = f"| {candidate.rank} " if include_rank else ""
        flags = _candidate_flags_text(candidate)
        duration = (
            f"{candidate.duration_seconds:.0f}s"
            if candidate.duration_seconds is not None
            else "unknown"
        )
        lines.append(
            (
                f"{rank_cell}| `{candidate.call_id}` | `{candidate.call_type}` | "
                f"{duration} | {candidate.transcript_turns} | {candidate.score:.1f} | "
                f"{candidate.sensibility_status} | {len(candidate.issue_findings)} | {flags} |"
            )
        )
    return lines


def _candidate_flags_text(candidate: CallCandidate) -> str:
    if not candidate.sensibility_flags:
        return "none"

    labels = [
        _sensibility_flag_evidence(flag, candidate)
        if flag.startswith("possible_verification_loop_")
        else flag
        for flag in candidate.sensibility_flags
    ]
    return _escape_table("; ".join(label for label in labels if label) or "none")


def _selected_findings_table(findings: list[tuple[CallCandidate, IssueFinding]]) -> list[str]:
    lines = ["| Call | Category | Severity | Source | Finding | Evidence |"]
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for candidate, finding in findings:
        lines.append(
            (
                f"| `{candidate.call_id}` | {finding.category} | {finding.severity} | "
                f"{finding.source_guess} | {_escape_table(finding.summary)} | "
                f"{_escape_table(finding.evidence)} |"
            )
        )
    return lines


def _selected_issue_count_table(findings: list[tuple[CallCandidate, IssueFinding]]) -> list[str]:
    counts: dict[str, int] = {}
    for _candidate, finding in findings:
        counts[finding.summary] = counts.get(finding.summary, 0) + 1
    lines = ["| Type of Error | Selected Calls |"]
    lines.append("| --- | ---: |")
    for summary, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {_escape_table(summary)} | {count} |")
    return lines


def _selected_automated_findings(
    candidates: list[CallCandidate],
) -> list[tuple[CallCandidate, IssueFinding]]:
    findings: list[tuple[CallCandidate, IssueFinding]] = []
    for candidate in candidates:
        findings.extend((candidate, finding) for finding in candidate.issue_findings)
        findings.extend(
            (candidate, _sensibility_flag_finding(flag, candidate))
            for flag in candidate.sensibility_flags
        )
    return findings


def _sensibility_flag_finding(flag: str, candidate: CallCandidate) -> IssueFinding:
    return IssueFinding(
        "review_flag",
        "medium",
        "conversation",
        _sensibility_flag_summary(flag),
        _sensibility_flag_evidence(flag, candidate),
    )


def _sensibility_flag_summary(flag: str) -> str:
    if flag.startswith("possible_verification_loop_"):
        return "Possible verification loop detected from repeated verification exchanges."
    if flag.startswith("repeated_utterance_count_"):
        return "Repeated non-verification utterances may indicate a loop."
    if flag.startswith("long_same_speaker_run_"):
        return "Long same-speaker run may indicate interruption, grouping, or stalled dialogue."
    if flag == "patient_role_drift_phrase":
        return "Patient bot may have drifted into agent-side role language."
    if flag == "too_few_turns_for_rich_review":
        return "Call has few turns, limiting the opportunity to judge sustained behavior."
    return flag.replace("_", " ").capitalize()


def _sensibility_flag_evidence(flag: str, candidate: CallCandidate) -> str:
    if flag.startswith("possible_verification_loop_"):
        return _verification_loop_evidence(candidate) or flag
    return flag


def _verification_loop_evidence(candidate: CallCandidate) -> str:
    if candidate.transcript_path is None:
        return ""

    turns = _read_transcript_turns(Path(candidate.transcript_path))
    if not turns:
        return ""

    details: list[tuple[str, str, int]] = []
    seen: dict[tuple[str, str], tuple[str, int]] = {}
    ordered_keys: list[tuple[str, str]] = []
    for turn in turns:
        normalized = re.sub(r"\W+", " ", turn.text.casefold()).strip()
        if len(normalized.split()) < 3 or not _is_verification_utterance(normalized):
            continue
        key = (turn.speaker, normalized)
        if key not in seen:
            seen[key] = (turn.text, 0)
            ordered_keys.append(key)
        original, count = seen[key]
        seen[key] = (original, count + 1)

    for key in ordered_keys:
        original, count = seen[key]
        if count > 1:
            details.append((key[0], original, count))

    if details:
        return "; ".join(
            f"{speaker} repeated {count} times: {text}"
            for speaker, text, count in details[:5]
        )

    pushback = _already_provided_pushback_details(turns)
    if pushback:
        return "; ".join(
            f"Patient Bot repeated already-provided pushback {count} times: {text}"
            for text, count in pushback[:5]
        )

    return ""


def _issue_counts(candidates: list[CallCandidate]) -> dict[str, int]:
    counts = {"policy": 0, "factual": 0, "flow": 0, "voice_quality": 0}
    for candidate in candidates:
        for finding in candidate.issue_findings:
            counts[finding.category] = counts.get(finding.category, 0) + 1
    return counts


def _issue_count_line(counts: dict[str, int]) -> str:
    return (
        f"Policy: {counts.get('policy', 0)} | "
        f"Factual: {counts.get('factual', 0)} | "
        f"Flow: {counts.get('flow', 0)} | "
        f"Voice quality: {counts.get('voice_quality', 0)}"
    )


def _rejection_lines(candidates: list[CallCandidate]) -> list[str]:
    lines = []
    for candidate in sorted(candidates, key=lambda item: (item.call_type, item.call_id)):
        failures = "; ".join(candidate.gate_failures)
        lines.append(f"- `{candidate.call_id}`: {failures}")
    return lines


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _escape_table(value: str) -> str:
    return " ".join(value.split()).replace("|", "\\|")


def _scenario_text(call_dir: Path) -> str:
    path = call_dir / "scenario.yaml"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _snippet(text: str, pattern: re.Pattern[str], *, radius: int = 90) -> str:
    match = pattern.search(text)
    if match is None:
        return _first_nonempty_line(text)
    start = max(match.start() - radius, 0)
    end = min(match.end() + radius, len(text))
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{' '.join(text[start:end].split())}{suffix}"


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return ""


def _metadata_text(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _call_type(call_dir: Path, metadata: dict[str, Any]) -> str:
    return _metadata_text(metadata, "call_type") or call_dir.parent.name


def _find_recording(call_dir: Path) -> Path | None:
    for name in ("recording.mp3", "recording.ogg", "recording.wav"):
        path = call_dir / name
        if path.exists():
            return path
    return None


def _read_transcript_turns(path: Path) -> list[TranscriptTurn]:
    if not path.exists():
        return []
    turns: list[TranscriptTurn] = []
    current_speaker: str | None = None
    current_text: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = SPEAKER_PATTERN.match(line)
        if match:
            if current_speaker is not None:
                turns.append(TranscriptTurn(current_speaker, " ".join(current_text).strip()))
            current_speaker = match.group(1)
            current_text = [match.group(2).strip()]
        elif current_speaker is not None:
            current_text.append(line)
    if current_speaker is not None:
        turns.append(TranscriptTurn(current_speaker, " ".join(current_text).strip()))
    return turns


def _duration_seconds(call_dir: Path, metadata: dict[str, Any]) -> tuple[float | None, str | None]:
    duration_sources = [
        (call_dir / "recording_metadata.json", ("duration",)),
        (call_dir / "post_call_summary.json", ("duration_seconds",)),
        (call_dir / "post_call_status.json", ("duration", "duration_seconds")),
    ]
    for path, keys in duration_sources:
        payload = _read_json(path)
        for key in keys:
            duration = _coerce_float(payload.get(key))
            if duration is not None:
                return duration, path.name

    for key in ("duration_seconds", "recording_duration_seconds"):
        call_payload = metadata.get("call")
        if isinstance(call_payload, dict):
            duration = _coerce_float(call_payload.get(key))
            if duration is not None:
                return duration, f"metadata.call.{key}"
        duration = _coerce_float(metadata.get(key))
        if duration is not None:
            return duration, f"metadata.{key}"

    event_duration = _duration_from_events(call_dir / "events.jsonl")
    if event_duration is not None:
        return event_duration, "events.jsonl"
    return None, None


def _duration_from_events(path: Path) -> float | None:
    if not path.exists():
        return None
    start_time: datetime | None = None
    end_time: datetime | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_time = _parse_iso_datetime(event.get("time"))
        if event_time is None:
            continue
        if event.get("event") == "call.boundary" and event.get("boundary") == "start":
            start_time = event_time
        if event.get("event") == "call.boundary" and event.get("boundary") == "end":
            end_time = event_time
        elif event.get("event") == "realtime.closed" and end_time is None:
            end_time = event_time
    if start_time is None or end_time is None:
        return None
    return max((end_time - start_time).total_seconds(), 0.0)


def _turn_taking_metrics(call_dir: Path, turns: list[TranscriptTurn]) -> TurnTakingMetrics:
    path = call_dir / "events.jsonl"
    if not path.exists():
        return TurnTakingMetrics(False, 0, 0, 0, 0.0)

    agent_over_patient_ids: set[str] = set()
    patient_over_agent_ids: set[str] = set()
    patient_response_cancelled = 0
    events_observed = False
    agent_speech_active = False
    patient_response_active_ids: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return TurnTakingMetrics(False, 0, 0, 0, 0.0)

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_name = event.get("event")
        if event_name == "agent_speech_during_bot_audio":
            events_observed = True
            agent_over_patient_ids.add(str(event.get("response_id") or len(agent_over_patient_ids)))
            continue
        if event_name == "patient_response.cancelled" and event.get("reason") == "agent_continued":
            events_observed = True
            patient_response_cancelled += 1
            continue

        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        event_type = payload.get("type")
        if event_type == "input_audio_buffer.speech_started":
            events_observed = True
            agent_speech_active = True
            agent_over_patient_ids.update(patient_response_active_ids)
            continue
        if event_type == "input_audio_buffer.speech_stopped":
            events_observed = True
            agent_speech_active = False
            continue
        if event_type == "response.output_audio_transcript.delta":
            events_observed = True
            response_id = str(payload.get("response_id") or payload.get("item_id") or "unknown")
            patient_response_active_ids.add(response_id)
            if agent_speech_active and response_id not in agent_over_patient_ids:
                patient_over_agent_ids.add(response_id)
            continue
        if event_type == "response.output_audio_transcript.done":
            events_observed = True
            response_id = str(payload.get("response_id") or payload.get("item_id") or "unknown")
            if agent_speech_active and response_id not in agent_over_patient_ids:
                patient_over_agent_ids.add(response_id)
            patient_response_active_ids.discard(response_id)
            continue
        if event_type == "conversation.item.input_audio_transcription.completed":
            events_observed = True
            continue

    adjustment = _turn_taking_score_adjustment(
        events_observed=events_observed,
        turns=turns,
        agent_over_patient=len(agent_over_patient_ids),
        patient_over_agent=len(patient_over_agent_ids),
        patient_response_cancelled=patient_response_cancelled,
    )
    return TurnTakingMetrics(
        events_observed,
        len(agent_over_patient_ids),
        len(patient_over_agent_ids),
        patient_response_cancelled,
        adjustment,
    )


def _turn_taking_score_adjustment(
    *,
    events_observed: bool,
    turns: list[TranscriptTurn],
    agent_over_patient: int,
    patient_over_agent: int,
    patient_response_cancelled: int,
) -> float:
    if not events_observed:
        return 0.0

    adjustment = 0.0
    clean_turn_taking = (
        len(turns) >= 8
        and agent_over_patient == 0
        and patient_over_agent == 0
        and patient_response_cancelled == 0
    )
    if clean_turn_taking:
        adjustment += 4.0

    adjustment -= min(agent_over_patient * 0.75, 3.0)
    adjustment -= min(patient_over_agent * 3.0, 12.0)
    return round(adjustment, 3)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gate_failures(
    call_dir: Path,
    *,
    duration_seconds: float | None,
    min_duration_seconds: float,
    recording_path: Path | None,
    transcript_path: Path,
    turns: list[TranscriptTurn],
) -> list[str]:
    failures: list[str] = []
    if duration_seconds is None:
        failures.append("duration_unknown")
    elif duration_seconds < min_duration_seconds:
        failures.append(f"duration_below_{min_duration_seconds:g}s")
    if recording_path is None:
        failures.append("recording_missing")
    elif recording_path.stat().st_size <= 0:
        failures.append("recording_empty")
    if not transcript_path.exists():
        failures.append("transcript_missing")
    elif transcript_path.stat().st_size <= 0:
        failures.append("transcript_empty")
    if not (call_dir / "metadata.json").exists():
        failures.append("metadata_missing")
    if not turns:
        failures.append("no_speaker_labeled_turns")
    return failures


def _sensibility_check(turns: list[TranscriptTurn]) -> tuple[str, list[str]]:
    flags: list[str] = []
    if len(turns) < 6:
        flags.append("too_few_turns_for_rich_review")

    speakers = {turn.speaker for turn in turns}
    if speakers != {"PGAI Agent", "Patient Bot"}:
        flags.append("missing_one_speaker")

    longest_run = _longest_same_speaker_run(turns)
    if longest_run >= 5:
        flags.append(f"long_same_speaker_run_{longest_run}")

    verification_repeated, other_repeated = _repeated_utterance_counts_by_context(turns)
    verification_repeated += _already_provided_pushback_count(turns)
    if verification_repeated >= 2:
        flags.append(f"possible_verification_loop_{verification_repeated}")
    if other_repeated >= 3:
        flags.append(f"repeated_utterance_count_{other_repeated}")

    patient_text = "\n".join(turn.text for turn in turns if turn.speaker == "Patient Bot")
    if META_DISCLOSURE_PATTERN.search(patient_text):
        flags.append("patient_meta_disclosure")
    if PATIENT_ROLE_DRIFT_PATTERN.search(patient_text):
        flags.append("patient_role_drift_phrase")

    severe = {
        "missing_one_speaker",
        "patient_meta_disclosure",
    }
    if severe.intersection(flags):
        return "fail", flags
    if any(flag.startswith("long_same_speaker_run_") for flag in flags):
        return "review", flags
    if any(flag.startswith("possible_verification_loop_") for flag in flags):
        return "review", flags
    if any(flag.startswith("repeated_utterance_count_") for flag in flags):
        return "review", flags
    if flags:
        return "review", flags
    return "pass", flags


def _automated_issue_scan(
    call_dir: Path,
    metadata: dict[str, Any],
    turns: list[TranscriptTurn],
    *,
    duration_seconds: float | None,
    gate_failures: list[str],
) -> list[IssueFinding]:
    findings: list[IssueFinding] = []
    transcript_text = "\n".join(f"{turn.speaker}: {turn.text}" for turn in turns)
    agent_text = "\n".join(turn.text for turn in turns if turn.speaker == "PGAI Agent")
    patient_text = "\n".join(turn.text for turn in turns if turn.speaker == "Patient Bot")
    scenario_blob = " ".join(
        value
        for value in (
            _metadata_text(metadata, "scenario_id"),
            _metadata_text(metadata, "runtime_scenario_id"),
            _metadata_text(metadata, "scenario_stem"),
            _scenario_text(call_dir),
        )
        if value
    ).casefold()

    _scan_policy_issues(findings, transcript_text, agent_text, patient_text, scenario_blob)
    _scan_factual_issues(findings, transcript_text, agent_text, patient_text, scenario_blob)
    _scan_flow_issues(findings, turns, patient_text, agent_text, scenario_blob)
    _scan_voice_quality_issues(
        findings,
        call_dir,
        duration_seconds=duration_seconds,
        gate_failures=gate_failures,
    )
    return _dedupe_findings(findings)


def _scan_policy_issues(
    findings: list[IssueFinding],
    transcript_text: str,
    agent_text: str,
    patient_text: str,
    scenario_blob: str,
) -> None:
    if META_DISCLOSURE_PATTERN.search(patient_text):
        findings.append(
            IssueFinding(
                "policy",
                "high",
                "patient_bot",
                "Patient bot may have disclosed the test or automation context.",
                _snippet(patient_text, META_DISCLOSURE_PATTERN),
            )
        )

    emergency_context = "emergency" in scenario_blob or re.search(
        r"\b(chest pain|can'?t breathe|cannot breathe|stroke|heart attack)\b",
        transcript_text,
        re.IGNORECASE,
    )
    emergency_redirect = re.search(
        r"\b(911|emergency room| er\b|urgent care|emergency services)\b",
        agent_text,
        re.IGNORECASE,
    )
    if emergency_context and not emergency_redirect:
        findings.append(
            IssueFinding(
                "policy",
                "high",
                "agent_bot",
                "Emergency-like scenario lacks an obvious urgent-care or 911 redirect.",
                "No direct transcript line: this issue is inferred from emergency context and the absence of an urgent-care or 911 redirect.",
            )
        )

    minor_context = "minor" in scenario_blob or re.search(
        r"\b(16|sixteen|parent|guardian|mom|mother|dad|father)\b",
        transcript_text,
        re.IGNORECASE,
    )
    consent_language = re.search(r"\b(parent|guardian|consent|minor)\b", agent_text, re.I)
    if minor_context and not consent_language:
        findings.append(
            IssueFinding(
                "policy",
                "medium",
                "agent_bot",
                "Minor or guardian context may not have been acknowledged by the agent.",
                "No direct transcript line: this issue is inferred from minor or guardian context and the absence of agent acknowledgement.",
            )
        )


def _scan_factual_issues(
    findings: list[IssueFinding],
    transcript_text: str,
    agent_text: str,
    patient_text: str,
    scenario_blob: str,
) -> None:
    if re.search(r"\bam i speaking with\b", agent_text, re.I) and re.search(
        r"\b(wrong patient|wrong person|caller is|not mine|not me)\b",
        patient_text,
        re.I,
    ):
        findings.append(
            IssueFinding(
                "factual",
                "high",
                "agent_bot",
                "Agent may have assumed or surfaced the wrong patient identity.",
                _snippet(transcript_text, re.compile(r"\b(wrong patient|caller is|not mine)\b", re.I)),
            )
        )

    if re.search(r"\bphone number\b", agent_text, re.I) and re.search(
        r"\b(that phone number is not mine|not my phone|wrong number)\b",
        patient_text,
        re.I,
    ):
        findings.append(
            IssueFinding(
                "factual",
                "high",
                "agent_bot",
                "Agent may have confirmed an incorrect phone number or stale record.",
                _snippet(transcript_text, re.compile(r"\b(phone number is not mine|wrong number)\b", re.I)),
            )
        )

    if ("office_hours" in scenario_blob or "office hours" in scenario_blob) and re.search(
        r"\b(saturday|sunday|weekend)\b",
        agent_text,
        re.I,
    ):
        findings.append(
            IssueFinding(
                "factual",
                "medium",
                "agent_bot",
                "Office-hours answer mentions weekend availability; verify against product facts.",
                _snippet(agent_text, re.compile(r"\b(saturday|sunday|weekend)\b", re.I)),
            )
        )

    high_confidence_fact = re.compile(
        r"\b(definitely covered|guaranteed|will be covered|fixed cost)\b",
        re.I,
    )
    if high_confidence_fact.search(agent_text):
        findings.append(
            IssueFinding(
                "factual",
                "medium",
                "agent_bot",
                "Agent gives high-confidence coverage or cost language that may need verification.",
                _snippet(agent_text, high_confidence_fact),
            )
        )


def _scan_flow_issues(
    findings: list[IssueFinding],
    turns: list[TranscriptTurn],
    patient_text: str,
    agent_text: str,
    scenario_blob: str,
) -> None:
    repeated_agent = _repeated_utterance_count(
        [turn for turn in turns if turn.speaker == "PGAI Agent"]
    )
    if repeated_agent >= 2:
        findings.append(
            IssueFinding(
                "flow",
                "medium",
                "agent_bot",
                "Agent appears to repeat the same prompt multiple times.",
                f"Repeated agent utterances: {repeated_agent}",
            )
        )

    longest_run = _longest_same_speaker_run(turns)
    if longest_run >= 5:
        findings.append(
            IssueFinding(
                "flow",
                "medium",
                "conversation",
                "Long same-speaker run may indicate interruption, grouping, or stalled dialogue.",
                f"Longest same-speaker run: {longest_run}",
            )
        )

    if len(turns) < 8:
        findings.append(
            IssueFinding(
                "flow",
                "low",
                "conversation",
                "Call has few turns, limiting the opportunity to judge sustained behavior.",
                f"Speaker-labeled turns: {len(turns)}",
            )
        )

    already_provided = re.compile(
        r"\bi already (?:gave|provided|shared|told|said|answered)\b",
        re.I,
    )
    if len(already_provided.findall(patient_text)) >= 2:
        findings.append(
            IssueFinding(
                "flow",
                "medium",
                "conversation",
                "Patient repeatedly indicates the agent is re-asking for already-provided verification.",
                _snippet(patient_text, already_provided),
            )
        )

    escalation = re.compile(
        r"\b("
        r"connect(?:ing)? you|transfer(?:ring)? you|representative|please wait|"
        r"can'?t proceed further|unable to proceed|support team"
        r")\b",
        re.I,
    )
    if escalation.search(agent_text) and not _escalation_appears_warranted(
        agent_text,
        scenario_blob,
    ):
        findings.append(
            IssueFinding(
                "flow",
                "medium",
                "agent_bot",
                "Agent escalated or transferred the call instead of resolving it in-bot.",
                _snippet(agent_text, escalation),
            )
        )


def _escalation_appears_warranted(agent_text: str, scenario_blob: str) -> bool:
    normalized_agent = agent_text.casefold()
    normalized_scenario = scenario_blob.casefold()

    if re.search(
        r"\b("
        r"can'?t proceed further|can'?t access your record|can'?t locate your record|"
        r"unable to proceed|can'?t check .* right now|can'?t process .* right now"
        r")\b",
        normalized_agent,
    ):
        return False

    if re.search(
        r"\b(?:do not|does not|should not|must not)\s+\w{0,20}\s*(?:escalate|transfer)\b",
        normalized_scenario,
    ):
        return False

    if (
        "records request" in normalized_scenario
        or "record sent" in normalized_scenario
        or "medical records" in normalized_scenario
    ):
        return bool(
            re.search(r"\b(record|records|authorization|release|fax|route)\b", normalized_agent)
        )

    if "no record" in normalized_scenario and "refill" in normalized_scenario:
        return bool(
            re.search(
                r"\b(new patient|callback|call back|right place|alternative|staff|support team)\b",
                normalized_agent,
            )
        )

    if "refill" in normalized_scenario:
        return bool(
            re.search(r"\b(documented|submitted|sent it|request is in|clinic support team)\b", normalized_agent)
            and re.search(r"\b(refill|medication)\b", normalized_agent)
        )

    if (
        "appropriately escalate" in normalized_scenario
        or "accept an escalation" in normalized_scenario
        or "office follow-up" in normalized_scenario
    ):
        return bool(
            re.search(
                r"\b(policy|paperwork|question|staff|support team|follow up|follow-up)\b",
                normalized_agent,
            )
        )

    if "emergency" in normalized_scenario:
        return bool(re.search(r"\b(911|emergency|urgent care| er\b)\b", normalized_agent))

    return False


def _scan_voice_quality_issues(
    findings: list[IssueFinding],
    call_dir: Path,
    *,
    duration_seconds: float | None,
    gate_failures: list[str],
) -> None:
    for failure in gate_failures:
        if failure.startswith("recording") or failure.startswith("transcript"):
            findings.append(
                IssueFinding(
                    "voice_quality",
                    "high",
                    "artifact",
                    "Required audio/transcript artifact failed a hard gate.",
                    failure,
                )
            )

    if duration_seconds is None:
        findings.append(
            IssueFinding(
                "voice_quality",
                "medium",
                "artifact",
                "Duration could not be determined from recording metadata or events.",
                str(call_dir),
            )
        )


def _dedupe_findings(findings: list[IssueFinding]) -> list[IssueFinding]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[IssueFinding] = []
    for finding in findings:
        key = (finding.category, finding.source_guess, finding.summary)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _score_candidate(
    *,
    duration_seconds: float | None,
    turns: list[TranscriptTurn],
    sensibility_status: str,
    sensibility_flags: list[str],
    gate_failures: list[str],
    issue_findings: list[IssueFinding],
    turn_taking: TurnTakingMetrics,
) -> float:
    if gate_failures or sensibility_status == "fail":
        return 0.0

    duration = duration_seconds or 0.0
    turn_count = len(turns)
    word_count = sum(len(turn.text.split()) for turn in turns)
    agent_turns = sum(1 for turn in turns if turn.speaker == "PGAI Agent")
    patient_turns = sum(1 for turn in turns if turn.speaker == "Patient Bot")
    total_speaker_turns = max(agent_turns + patient_turns, 1)
    balance = 1.0 - (abs(agent_turns - patient_turns) / total_speaker_turns)

    duration_score = min(duration, 240.0) / 240.0 * 35.0
    turn_score = min(turn_count, 36) / 36.0 * 35.0
    word_score = min(word_count, 700) / 700.0 * 10.0
    balance_score = balance * 15.0
    complexity_bonus = min(max(turn_count - 8, 0), 10) * 0.5
    review_penalty = 8.0 if sensibility_status == "review" else 0.0
    flag_penalty = min(sum(_sensibility_flag_penalty(flag) for flag in sensibility_flags), 16.0)
    issue_bonus = _issue_opportunity_bonus(issue_findings)
    issue_penalty = _issue_source_penalty(issue_findings)

    return round(
        max(
            duration_score
            + turn_score
            + word_score
            + balance_score
            + complexity_bonus
            + issue_bonus
            + turn_taking.score_adjustment
            - review_penalty
            - flag_penalty
            - issue_penalty,
            0.0,
        ),
        3,
    )


def _issue_opportunity_bonus(findings: list[IssueFinding]) -> float:
    reviewable_findings = [
        finding
        for finding in findings
        if _agent_bug_issue_signature(finding) is not None
    ]
    categories = {finding.category for finding in reviewable_findings}
    return min(
        sum(_finding_bug_value(finding) for finding in reviewable_findings)
        + len(categories) * 2.0,
        24.0,
    )


def _sensibility_flag_penalty(flag: str) -> float:
    if flag == "patient_role_drift_phrase":
        return 8.0
    if (
        flag.startswith("long_same_speaker_run_")
        or flag.startswith("repeated_utterance_count_")
        or flag.startswith("possible_verification_loop_")
    ):
        return 3.0
    return 2.0


def _issue_source_penalty(findings: list[IssueFinding]) -> float:
    penalty = 0.0
    for finding in findings:
        if finding.source_guess not in {"patient_bot", "artifact"}:
            continue
        if finding.severity == "high":
            penalty += 4.0
        elif finding.severity == "medium":
            penalty += 2.0
    return min(penalty, 10.0)


def _longest_same_speaker_run(turns: list[TranscriptTurn]) -> int:
    longest = 0
    current = 0
    previous: str | None = None
    for turn in turns:
        if turn.speaker == previous:
            current += 1
        else:
            current = 1
            previous = turn.speaker
        longest = max(longest, current)
    return longest


def _repeated_utterance_count(turns: list[TranscriptTurn]) -> int:
    verification_repeated, other_repeated = _repeated_utterance_counts_by_context(turns)
    return verification_repeated + other_repeated


def _repeated_utterance_counts_by_context(turns: list[TranscriptTurn]) -> tuple[int, int]:
    counts: dict[tuple[str, str], int] = {}
    for turn in turns:
        normalized = re.sub(r"\W+", " ", turn.text.casefold()).strip()
        if len(normalized.split()) < 3:
            continue
        key = (turn.speaker, normalized)
        counts[key] = counts.get(key, 0) + 1
    verification_repeated = 0
    other_repeated = 0
    for (_speaker, normalized), count in counts.items():
        if count <= 1:
            continue
        repeated = count - 1
        if _is_verification_utterance(normalized):
            verification_repeated += repeated
        else:
            other_repeated += repeated
    return verification_repeated, other_repeated


def _is_verification_utterance(normalized: str) -> bool:
    if re.search(r"\b\d{3}\s+\d{3}\s+\d{4}\b", normalized):
        return True
    return bool(
        re.search(
            r"\b("
            r"date of birth|dob|phone number|full phone number|number you have on file|"
            r"name|first name|last name|spell|spelling|confirm|correct|records?"
            r")\b",
            normalized,
        )
    )


def _already_provided_pushback_count(turns: list[TranscriptTurn]) -> int:
    patient_text = "\n".join(turn.text for turn in turns if turn.speaker == "Patient Bot")
    count = len(_already_provided_pushback_pattern().findall(patient_text))
    if count < 2:
        return 0
    return count


def _already_provided_pushback_details(turns: list[TranscriptTurn]) -> list[tuple[str, int]]:
    pushbacks = [
        turn.text
        for turn in turns
        if turn.speaker == "Patient Bot"
        and _already_provided_pushback_pattern().search(turn.text)
    ]
    if len(pushbacks) < 2:
        return []
    return [(pushbacks[0], len(pushbacks))]


def _already_provided_pushback_pattern() -> re.Pattern[str]:
    return re.compile(r"\bi already (?:gave|provided|shared|told|said|answered)\b", re.I)


def _friendly_now() -> str:
    return utc_now_iso()


if __name__ == "__main__":
    raise SystemExit(main())
