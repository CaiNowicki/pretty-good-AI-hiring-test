# Call 001 Calibration Review

Source artifact: `artifacts/calls/call-001/transcript.txt`

Status: internal calibration only. Do not mark Phase 1 successful from this call.

## Patient Bot Issues

- The patient bot spoke during the call-recording and Spanish-language preamble instead of waiting for a real agent opening.
- The patient bot asked to schedule before the agent had offered a "how may I help" style service opening.
- The patient bot provided its name in a way that did not flow naturally with the surrounding intake conversation.
- The patient bot frequently interrupted or talked over the agent; this should be prevented in normal scenarios and reserved for explicit interruption tests.
- The patient bot briefly used scheduler-role language, saying it would check or adjust the time itself.
- After the first accepted appointment offer, the bot kept participating in a degraded follow-on conversation instead of closing or calmly re-confirming once.

## Scheduler Agent Candidate Bugs

### C001-BR-01: Agent Invented Date Of Birth For New Patient

Severity: Medium

Evidence:

- `15:18:43`: Patient bot gives first name: "James."
- `15:18:52`: Patient bot gives last name: "Carter."
- `15:19:03`: Agent says the profile has been created and states date of birth is July 4, 2000.
- `15:19:05`: Patient corrects it: "My date of birth is March 14, 1987, not July 4, 2000."

Why it matters:

For a new patient flow, inventing or assuming a birthdate before collecting it is a patient-identity and scheduling-quality issue. The agent should ask for DOB or clearly identify a demo placeholder before treating it as patient data.

Expected behavior:

The agent should ask the patient for date of birth before confirming a profile, or explicitly state that a demo placeholder is being used and request confirmation.

### C001-BR-02: Agent Hallucinated A New Conversation After Initial Booking Acceptance

Severity: Medium

Evidence:

- `15:19:23`: Agent begins offering a morning opening.
- `15:19:23`: Patient says, "That time works for me."
- After that point the call degrades: confirmation details shift from Tuesday July 15 at 9:00 AM, to Tuesday June 30 at 12:45 PM, to Tuesday July 7 at 10:30 AM, with the agent later asking for a reschedule reason even though this was initially a new booking.

Why it matters:

After the patient accepts an offered slot, the agent should maintain a single booking thread. Shifting dates and reframing the interaction as a reschedule creates uncertainty about whether the appointment is booked and what details are final.

Expected behavior:

The agent should confirm one appointment date/time/provider/location, ask any required follow-up once, then close cleanly or send details. If details change, it should explain the change rather than starting a new scheduling/rescheduling thread.

## Review Boundary

Everything after the first "That time works for me" is lower-confidence evidence because both sides begin degrading. Use this call to guide the next smoke test and candidate bug list, but reproduce strong issues in cleaner final calls before relying on them in the final report.
