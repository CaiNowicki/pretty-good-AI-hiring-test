# Deliverables Checklist

## Required GitHub Contents

- Working Python voice-bot code.
- `README.md` with setup and run instructions.
- `.env.example` with required variables and no secrets.
- Architecture doc with 1-2 paragraphs explaining system design and choices.
- Minimum 10 submitted call recordings in `ogg` or `mp3`.
- Minimum 10 speaker-labeled transcripts with both sides of each conversation.
- Bug report with useful issues and evidence.
- Loom walkthrough link.
- Five-minute screen recording showing AI-assisted debugging and iteration.

## Recommended Repository Shape

```text
README.md
.env.example
docs/
  PROJECT_PLAN.md
  ARCHITECTURE_DESIGN.md
  CALL_SCENARIOS.md
  DELIVERABLES.md
src/
  voicebot/
tests/
artifacts/
  calls/
    appointment_scheduling/
      call-001/
    medication_refill/
      call-001/
    information_gathering/
      call-001/
    orthopedic_edge_cases/
      call-001/
    difficult_call_handling/
      call-001/
  bug-report.md
```

The `src/`, `tests/`, and `artifacts/` folders should be added during implementation, not during planning.

## README Requirements

The final README should include:

- What the project does.
- Safety warning that the app only calls `+18054398008`.
- Setup steps.
- Environment variables.
- How to run a dry run.
- How to run one scenario.
- How to run a batch.
- Where recordings, transcripts, and reports are written.
- Known limitations.

## Bug Report Format

Use one entry per meaningful issue:

```text
## BR-001: Agent confirmed a weekend appointment

Severity: High
Call: artifacts/calls/call-005/transcript.txt at 01:23
Recording: artifacts/calls/call-005/recording.mp3

What happened:
The patient asked for Sunday at 10 AM, and the agent appeared to confirm it.

Why it matters:
If the practice is closed on weekends, this creates a failed appointment and a poor patient experience.

Expected behavior:
The agent should say the office is closed on weekends and offer valid weekday times.
```

Do not cite manual account setup observations as final evidence. Reproduce any suspected issue in one of the submitted bot calls, then cite the transcript and recording from that call.

## Loom Outline

Keep it under five minutes:

1. Problem framing: testing an AI phone agent as a realistic patient.
2. Architecture: telephony, realtime patient bot, artifacts, analysis.
3. Demo: one short transcript and recording snippet.
4. Findings: strongest bugs and why they matter.
5. Iteration: what changed after early calls.

## AI Debugging Screen Recording

Show a real fix, not a staged narrative:

- The symptom from a failed or awkward call.
- The prompt given to the AI assistant.
- The diagnosis.
- The code or prompt change.
- The verification run.

Good candidates:

- Audio format mismatch.
- Bot interruption handling.
- Transcript speaker-labeling bug.
- Call duration or hangup condition issue.
- Scenario prompt causing unnatural speech.
