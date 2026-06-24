# Call 002 Calibration Review

Source artifact: call-002 transcript notes from manual review.

Status: internal calibration only. Use this call to guide the next run and
candidate bug list; rely on a cleaner submitted call before treating these as
final bug-report evidence.

## Patient Bot Issues

- The patient bot volunteered unrelated details, including a no-referral answer
  and a morning preference, when the agent had not asked for them.
- The patient bot still interrupted the agent during the scheduling portion of
  the call. Normal scenarios need more conservative turn timing; interruption
  behavior should remain isolated to explicit barge-in tests.

## Scheduler Agent Candidate Bugs

### C002-BR-01: Agent Repeated Appointment-Type Classification After Confirmation

Severity: Low

Evidence:

- The agent asked whether the caller wanted a new patient consultation.
- After the caller indicated that was the request, the agent asked again whether
  the visit was a follow-up or a routine visit.

Why it matters:

Repeating mutually exclusive classification questions can make the caller think
the agent lost context or did not accept the earlier answer. It also increases
the chance that a patient changes their answer just to fit the agent's options.

Expected behavior:

Once the caller confirms a new patient consultation, the agent should preserve
that classification and move to the next necessary intake or scheduling step.
If the agent needs a more specific subtype, it should explain why the prior
answer is insufficient.

### C002-BR-02: Agent Offered Transfer But Then Ended The Call

Severity: Medium

Evidence:

- The agent offered to transfer the caller.
- Instead of completing the transfer or confirming that no transfer was needed,
  the agent ended the call.

Why it matters:

A transfer offer creates an expectation that the caller will either be connected
to another person or asked for permission to end the call. Ending immediately
can strand the patient before the scheduling task is complete.

Expected behavior:

After offering a transfer, the agent should either complete the handoff, clearly
state that transfer is unavailable, or confirm whether the caller wants anything
else before ending the call.

## Prompt And Timing Follow-Up

- Tighten patient instructions so the bot answers only the latest question and
  does not add unrelated facts, preferences, or referral comments.
- Add deterministic handling for repeated appointment-type questions so the bot
  restates "new patient consultation" instead of drifting into follow-up or
  routine-visit categories.
- Increase conservative turn-taking delay for normal scenarios before the next
  smoke call.
