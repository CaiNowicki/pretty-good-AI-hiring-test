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
    type_counts: dict[str, int] = {}
    for candidate in eligible:
        if len(selected) >= top_n:
            break
        if type_counts.get(candidate.call_type, 0) >= max_per_call_type:
            continue
        selected.append(candidate)
        type_counts[candidate.call_type] = type_counts.get(candidate.call_type, 0) + 1

    if len(selected) < top_n:
        already_selected = {candidate.call_dir for candidate in selected}
        for candidate in eligible:
            if len(selected) >= top_n:
                break
            if candidate.call_dir in already_selected:
                continue
            selected.append(candidate)
            already_selected.add(candidate.call_dir)

    return [replace(candidate, rank=index) for index, candidate in enumerate(selected, start=1)]


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
    needs_review = [
        candidate
        for candidate in selected
        if candidate.sensibility_status == "review"
    ]
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
    if needs_review:
        lines.extend(["## Selected Calls With Review Flags", ""])
        lines.extend(_candidate_table(needs_review, include_rank=True))
        lines.append("")

    selected_with_issues = [candidate for candidate in selected if candidate.issue_findings]
    if selected_with_issues:
        lines.extend(["## Automated Issues In Selected Calls", ""])
        lines.extend(_issue_table(selected_with_issues))
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
        flags = "; ".join(candidate.sensibility_flags) or "none"
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


def _issue_table(candidates: list[CallCandidate]) -> list[str]:
    lines = ["| Call | Category | Severity | Source | Finding | Evidence |"]
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for candidate in candidates:
        for finding in candidate.issue_findings:
            lines.append(
                (
                    f"| `{candidate.call_id}` | {finding.category} | {finding.severity} | "
                    f"{finding.source_guess} | {_escape_table(finding.summary)} | "
                    f"{_escape_table(finding.evidence)} |"
                )
            )
    return lines


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

    repeated = _repeated_utterance_count(turns)
    if repeated >= 3:
        flags.append(f"repeated_utterance_count_{repeated}")

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
    _scan_flow_issues(findings, turns, transcript_text, agent_text)
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
                _first_nonempty_line(transcript_text),
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
                _snippet(transcript_text, re.compile(r"\b(16|sixteen|mom|mother|guardian)\b", re.I)),
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
    transcript_text: str,
    agent_text: str,
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

    if re.search(r"\b(connect|transfer|representative|please wait)\b", agent_text, re.I) and re.search(
        r"\b(test line|goodbye)\b",
        transcript_text,
        re.I,
    ):
        findings.append(
            IssueFinding(
                "flow",
                "medium",
                "agent_bot",
                "Transfer path appears to end at the test line instead of a meaningful resolution.",
                _snippet(transcript_text, re.compile(r"\b(test line|goodbye)\b", re.I)),
            )
        )


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
    flag_penalty = min(len(sensibility_flags) * 2.0, 8.0)
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
        if finding.source_guess in {"agent_bot", "conversation", "unknown"}
    ]
    categories = {finding.category for finding in reviewable_findings}
    return min(len(categories) * 2.0 + len(reviewable_findings) * 0.5, 8.0)


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
    counts: dict[tuple[str, str], int] = {}
    for turn in turns:
        normalized = re.sub(r"\W+", " ", turn.text.casefold()).strip()
        if len(normalized.split()) < 3:
            continue
        key = (turn.speaker, normalized)
        counts[key] = counts.get(key, 0) + 1
    return sum(count - 1 for count in counts.values() if count > 1)


def _friendly_now() -> str:
    return utc_now_iso()


if __name__ == "__main__":
    raise SystemExit(main())
