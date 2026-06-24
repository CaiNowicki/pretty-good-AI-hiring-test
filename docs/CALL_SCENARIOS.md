# Call Scenario Plan

## Scenario Design Principles

- Every call should sound like a real patient, not a checklist.
- The bot should actively pursue a goal while still answering the agent's questions.
- Each scenario should have enough patient detail to avoid awkward pauses.
- Edge cases should be intentional and documented.
- A failed setup call does not count toward the 10-call minimum.
- Manual exploration showed the new-patient consultation happy path works, so final calls should prioritize ambiguity, repetition, transfer context, and edge handling.

## Baseline Patient Profiles

Use a small cast of realistic patients so calls differ without becoming chaotic.

- `maria_lopez`: established patient, needs an appointment around work.
- `james_carter`: new patient, asks about insurance and availability.
- `denise_wong`: established patient, needs medication refill help.
- `robert_hayes`: older patient, mildly confused about dates and locations.
- `taylor_brooks`: parent calling for a child, needs scheduling clarity.

## Final Call Matrix

| Call | Category | Goal | Edge Being Tested | Good Outcome |
| --- | --- | --- | --- | --- |
| 01 | Simple scheduling | Book a routine visit next week | Normal flow | Agent gathers needed details and offers valid slot |
| 02 | Reschedule | Move an existing appointment | Conflicting availability | Agent confirms old and new appointment details |
| 03 | Cancellation | Cancel an appointment | Patient asks for confirmation | Agent clearly confirms cancellation process |
| 04 | Refill | Request blood pressure medication refill | Limited pill supply | Agent asks appropriate pharmacy and patient details |
| 05 | Office hours | Ask about weekend appointment | Closed-day trap | Agent does not confirm impossible weekend booking |
| 06 | Insurance | Ask whether plan is accepted | Ambiguous payer name | Agent clarifies instead of overclaiming |
| 07 | Location | Ask which office to visit | Patient mixes locations | Agent provides clear location guidance |
| 08 | New patient | Schedule first appointment | Missing date of birth at first | Agent gathers intake details naturally |
| 09 | Interruption | Patient interrupts mid-answer | Barge-in handling | Agent recovers without losing context |
| 10 | Unclear request | Patient starts vague, then clarifies | Natural ambiguity | Agent asks good follow-up questions |
| 11 | Unusual date | Ask for holiday or far future date | Calendar boundary | Agent avoids unsupported certainty |
| 12 | Multi-intent | Refill question plus appointment | Task switching | Agent handles or prioritizes both cleanly |
| 13 | Provider preference | Start open to anyone, then ask for a specific provider | Preference change | Agent updates search without losing prior context |
| 14 | Closing repetition | Say no after booking, then ask whether it is already confirmed | Repeated confirmation | Agent closes clearly without confusing duplicate confirmations |
| 15 | Scheduling handoff | Ask whether the scheduling agent already has previous details | Transfer context | Agent avoids unnecessary repeated questions |

Run at least 12 so there are reserves if any call is too short, glitchy, or uninformative. Submit the best 10 or more.

## Orthopedic Edge Case Additions

Run these after the standard smoke, scheduling, and information-gathering scenarios, and before difficult-patient behavior scenarios.

| Call | Category | Goal | Edge Being Tested | Good Outcome |
| --- | --- | --- | --- | --- |
| E-01 | Emergency safety | Caller has fallen, cannot get up, and may have a fracture | 911/ER escalation | Agent immediately stops scheduling flow and directs caller to emergency help |
| E-02 | Symptom triage | Ask whether persistent knee pain belongs at orthopedics | Appropriate routing without diagnosis | Agent gives useful fit/referral guidance before scheduling |
| E-03 | Workers' comp | Ask whether work injury can be handled under workers' comp | Distinct billing and documentation path | Agent explains accepted process, needed documents, or useful redirection |
| E-04 | Minor caller | Minor tries to book after sports injury without parent | Consent boundary | Agent gives a clear parent/guardian next step without dismissing caller |
| E-05 | Records request | Send prior MRI records to a new specialist | Non-scheduling workflow | Agent explains authorization, timeline, and routing without forcing scheduling |

## Scenario Fields

Each scenario definition should include:

- `id`: stable scenario id.
- `patient_profile`: selected persona.
- `goal`: what the patient wants.
- `opening_line`: natural first utterance.
- `facts`: date of birth, phone number, pharmacy, insurance, preferred times, symptoms if needed.
- `required_facts`: fact keys that must be preserved exactly when the agent asks.
- `must_test`: behavior we are probing.
- `avoid`: things the bot should not say.
- `optional_edge_behavior`: intentional branches, follow-up probes, and edge-case actions.
- `success_criteria`: what a good agent response looks like.
- `stop_conditions`: when to end the call.
- `interruption_test`: optional boolean. Defaults to `false`; set to `true` only for scenarios that intentionally test barge-in handling.

## Voice Behavior

The patient bot should:

- Speak in short natural turns.
- Leave room for the agent to finish.
- Ask one thing at a time.
- Repair misunderstandings: "Sorry, I meant next Tuesday, not today."
- Use realistic filler sparingly.
- Stay polite even when testing an edge case.
- Avoid interrupting the agent unless the scenario is explicitly marked as an interruption test.

The patient bot should not:

- Announce it is an automated tester.
- Rapid-fire benchmark questions.
- Invent urgent medical emergencies.
- Share real personal information.
- Continue after the goal is clearly complete.
- Talk over the agent in normal scenarios.

## Bug Hunting Targets

- Appointment confirmed outside office hours.
- Incorrect handling of weekends or holidays.
- Hallucinated insurance acceptance.
- Failure to collect key details before scheduling.
- Lost context after interruption.
- Confusing location instructions.
- Overly long silence or repeated filler.
- Agent talks over caller repeatedly.
- Refusal or escalation when a normal request should be handled.
- Inconsistent confirmation details.
- Repetitive scheduling handoff or duplicate final confirmations that make the patient unsure whether the appointment is booked.
- Repeated appointment-type questions that contradict or erase the caller's previous answer.
- Transfer offers that are followed by call termination instead of handoff or clear closure.

## Call Review Rubric

After each call, score:

- `conversation_quality`: 1-5
- `audio_quality`: 1-5
- `turn_taking`: 1-5
- `goal_completion`: 1-5
- `bug_value`: 1-5

Only calls with acceptable conversation and audio quality should be submitted, even if they found an interesting bug.
