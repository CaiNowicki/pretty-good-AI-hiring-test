# Bug Analysis Workflow

Use this while the final scenario calls are still being run and artifacts are
arriving. The goal is to turn recordings and transcripts into a small, strong,
evidence-backed bug report.

## Current Readiness Snapshot

Snapshot taken June 25, 2026 while scenario calls were still in progress:

- 50 call folders currently have non-empty recording and transcript artifacts.
- 11 call folders are retry/setup/noise candidates because they lack a usable
  recording or non-empty transcript.
- Reviewable calls by category: appointment scheduling 24, information
  gathering 8, medication refill 2, orthopedic edge cases 1, smoke 2, legacy
  flat calibration 13.

Treat this as a moving snapshot, not the final submitted call count.

## Triage Order

1. Review grouped final-call artifacts before legacy flat calibration calls.
2. Start with categories most likely to yield patient-impacting bugs:
   appointment scheduling, medication refill, orthopedic edge cases, then
   information gathering.
3. Skip calls with empty transcripts, missing recordings, or obvious setup
   failures unless they are being investigated as harness bugs rather than
   PGAI product bugs.
4. For each promising issue, verify the transcript against the recording before
   promotion.

## First-Pass Tags

Use these tags in notes and candidate bug entries:

- `policy`: unsafe medical, emergency, privacy, identity, or records handling.
- `factual`: incorrect office, provider, insurance, medication, timing, or
  availability claim.
- `flow`: lost context, repeated questions, contradictory instructions,
  failed handoff, or premature hangup.
- `voice`: talk-over, long silence, confusing turn-taking, audio intelligibility,
  or repeated filler.
- `harness`: caller-bot, transcript, artifact, or recording issue. Do not cite
  as a PGAI product bug.

## Review Rubric

For each reviewable call, score:

- `conversation_quality`: 1-5
- `audio_quality`: 1-5
- `turn_taking`: 1-5
- `goal_completion`: 1-5
- `bug_value`: 1-5

Calls with weak audio or obvious harness interference should be treated as
backup evidence only, even if they contain an interesting moment.

## Evidence Template

```text
Candidate ID:
Category:
Severity:
Status: candidate | promoted | rejected | needs reproduction
Call:
Scenario:
Transcript:
Recording:
Timestamp:

What happened:

Why it matters:

Expected behavior:

Actual behavior:

Confidence notes:
```

## Promotion Rules

Promote a candidate bug when it has:

- A reviewable call with recording and speaker-labeled transcript.
- A clear patient impact or quality impact.
- A concrete expected behavior.
- A specific timestamp or short transcript excerpt.
- Recording verification for the cited moment.

Reject or defer when:

- The transcript is empty, mis-labeled, or contradicted by the recording.
- The issue was caused by the patient bot talking over the agent in a normal
  non-interruption scenario.
- The observation only came from manual product exploration and was not
  reproduced in a submitted bot call.
- The call is too short or garbled to support the claim.

## Likely Bug Families To Watch

- Identity assumptions before the caller provides or confirms identity.
- Repeated or unexplained identity-verification failure.
- Weekend, holiday, closed-hours, or far-future scheduling certainty.
- Duplicate appointment-type questions after the caller already answered.
- Transfer offers followed by hangup or unclear closure.
- Medication refill requests accepted without enough patient, pharmacy, or
  medication detail.
- Emergency or urgent symptoms routed into normal scheduling.
- Records, minors, workers' comp, or insurance questions handled with
  overconfident generic answers.
