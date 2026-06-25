# Candidate Bugs

These are working notes for recurrent scheduler-agent issues observed in smoke
calls. Promote only cleaner, well-evidenced items into the final bug report.

## Bug Analysis Queue

Status: Ready for transcript and recording review as final scenario calls finish.

Use `docs/BUG_ANALYSIS_WORKFLOW.md` for the review order, scoring rubric,
first-pass tags, and promotion rules.

Current intake rules:

- Review grouped final-call artifacts before legacy calibration calls.
- Do not promote calls with missing recordings, empty transcripts, or obvious
  harness interference.
- Promote fewer, stronger issues with timestamped evidence and recording
  verification.
- Keep rejected candidates in notes when they explain why an issue was not
  strong enough for the final report.

## CB-IDENTITY-01: Agent Assumes Or Mentions Patient Name Before Collecting It

Severity: Medium

Status: Recurrent candidate bug. Needs one clean final-call reproduction if used
in the final report.

Evidence:

- `call-003`, `2026-06-24T16:08:59+00:00`: Agent says, "Am I speaking with James?"
  during the recording preamble, before the patient has provided a name in that
  call.
- `call-003`, `2026-06-24T16:09:13+00:00`: Agent repeats, "Am I speaking with
  James? How can I help you today?"
- `call-004`, `2026-06-24T16:54:24+00:00`: Agent opens with "is this James?"
  while also asking how it can help.
- `call-006`, `2026-06-24T18:04:45+00:00`: Agent asks, "Am I speaking with
  James?" before the patient has confirmed identity.
- `call-006`, `2026-06-24T18:05:00+00:00`: Agent repeats, "Am I speaking with
  James? How can I help you today?"

Adjacent evidence:

- `call-002`, `2026-06-24T16:02:16+00:00`: Agent says, "This is James. How can
  I help you today?" This may be the agent self-identifying as James, but it is
  confusing because James is also the patient persona.
- `call-005`, `2026-06-24T17:45:52+00:00`: Agent again says, "This is James.
  How can I help you today?"

Why it matters:

For new-patient intake, the agent should not appear to know or assume the
caller's name before collecting or verifying identity. This can confuse callers,
especially when the agent's self-introduction uses the same name as the patient
persona, and it can make the system seem to be using stale or invented patient
context.

Expected behavior:

The agent should either greet generically and ask how it can help, or clearly
ask for identity verification after the caller states the reason for calling.
If caller identity is inferred from phone metadata or an existing record, the
agent should phrase it as a verification step and avoid mixing that with its own
name.

## CB-IDENTITY-02: Agent Repeats "I Can't Verify You" Despite Caller Participation

Severity: Medium

Status: Observation / potential bug. Needs transcript-backed reproduction before
being used in the final report.

Evidence:

- Manual observation: the agent bot has repeatedly said variants of "I can't
  verify you" across calls.
- Suspected contributing factor: repeated use of the same patient personas may
  be causing the agent to rely on stale or hallucinated identity context instead
  of the facts provided in the current call. This is only a hypothesis until
  confirmed against call transcripts and scenario/persona inputs.

Why it matters:

Identity verification should be strict, but it should also be explainable and
grounded in the current conversation. Repeatedly refusing verification without a
clear mismatch can block legitimate callers, create confusion, and make the
agent appear to be using hidden or incorrect patient details.

Expected behavior:

The agent should state exactly which required identifier is missing or
mismatched, allow the caller to provide or correct that identifier, and avoid
repeating a generic verification failure when the caller has supplied the
requested information.
