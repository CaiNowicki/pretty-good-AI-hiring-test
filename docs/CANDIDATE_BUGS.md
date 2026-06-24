# Candidate Bugs

These are working notes for recurrent scheduler-agent issues observed in smoke
calls. Promote only cleaner, well-evidenced items into the final bug report.

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
