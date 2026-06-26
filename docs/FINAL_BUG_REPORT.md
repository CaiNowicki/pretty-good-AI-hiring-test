# Bug Report - Pivot Point Orthopedics Voice Agent

Generated from review of the non-legacy call set in `artifacts/calls/`.

## Scope

Found: 89 non-legacy call directories.

Reviewed: 80 non-legacy transcript files.

Excluded from primary causal analysis:

- 9 directories had no transcript and could not be reviewed: `appointment_scheduling/call-038`, `appointment_scheduling/call-039`, `information_gathering/call-001`, `information_gathering/call-002`, `information_gathering/call-003`, `information_gathering/call-004`, `information_gathering/call-005`, `medication_refill/call-001`, `medication_refill/call-002`.
- 3 transcripts were empty: `information_gathering/call-006`, `medication_refill/call-003`, `medication_refill/call-004`.
- 15 calls contained patient-bot artifacts such as internal reasoning or persona leakage. These calls are not used as primary evidence where the artifact could have caused the failure. Agent bugs that occurred before, or independently of, the patient-bot artifact are still listed in the appendix for traceability.

The report below focuses on agent-bot behavior. Patient-bot behavior is mentioned only when it materially limits interpretation.

## Executive Summary

The dominant failure mode is identity verification. In clean, non-empty calls, the agent repeatedly opens as though the caller is "James", continues with verification after the caller corrects the identity, asks for information already supplied, misreads or truncates patient-provided data, and often escalates after gathering enough information to proceed.

This prevents many scenarios from being tested on their merits. Appointment scheduling, medication refill, worker's comp, records, and minor-consent scenarios often collapse into the same verification failure before the task-specific workflow can complete.

There are also several higher-risk behavior classes:

- The agent exposes or relies on stale/fabricated patient data, especially the recurring `941-842-0514` phone number.
- The agent uses internal demo override language such as "for demo purposes, I'll accept it."
- The agent sometimes acts on records after verification has failed.
- The agent sends a text confirmation before resolving a phone-number mismatch.

## Findings

### AGT-001 - Agent Assumes the Caller Is James Before Verification

Severity: High

The agent frequently opens with "Am I speaking with James?" even when the patient immediately says they are not James. This creates a wrong-patient disclosure risk and sets the rest of the call on an unstable identity path.

Examples:

- `appointment_scheduling/call-006`: caller says this is Maria Lopez and that the agent may have the wrong patient.
- `information_gathering/call-021`: caller says this is Dmitri Volkov, not James.
- `smoke/call-002`: caller says this is Maya Patel, not James.

Expected behavior: greet neutrally, then verify identity from caller-provided information before surfacing a patient name.

### AGT-002 - Agent Uses Internal Demo Override Language

Severity: High

The agent sometimes says the birthdate does not match records, then proceeds anyway "for demo purposes." This exposes internal test state and tells the caller the agent is bypassing verification.

Examples:

- `appointment_scheduling/call-028`: "The birthday doesn't match our records, but for demo purposes, I'll accept it."
- `difficult_call_handling/call-001`: same pattern before scheduling.
- `orthopedic_edge_cases/call-005`: same pattern before booking a minor's appointment.

Expected behavior: do not expose demo/test logic. If verification fails, explain that the agent cannot proceed and provide appropriate next steps.

### AGT-003 - Agent Surfaces Stale or Fabricated Phone Numbers

Severity: High

The agent repeatedly reads back an on-file phone number the caller did not provide. The recurring number `941-842-0514` appears across unrelated patients. In several calls, the caller rejects the number as not theirs.

Examples:

- `medication_refill/call-007`: agent gives `941-842-0514`; Dmitri Volkov says it is not his number and gives `5085550341`.
- `smoke/call-002`: agent gives the same `941-842-0514` number during Maya Patel's call.
- `orthopedic_edge_cases/call-005`: agent says it sent a confirmation, then reveals the on-file number is `941-842-0514`, while the patient gives `555-684-2190`.

Expected behavior: do not volunteer or confirm patient contact data until the agent has matched the correct record. If lookup returns a conflicting number, treat it as a verification failure, not as confirmed patient data.

### AGT-004 - Agent Re-Asks for Already Provided Verification Data

Severity: High

The agent gets stuck asking for names, spellings, dates of birth, or phone numbers that the caller has already provided. The patient often has to say they already gave the information.

Examples:

- `appointment_scheduling/call-018`: the agent repeatedly asks Robert Hayes to spell his name and last name after the caller already did so.
- `medication_refill/call-007`: the caller says they already gave the spelling of the last name.
- `smoke/call-002`: the caller says they already gave the date of birth.

Expected behavior: retain verified fields during the call and only re-ask when the agent can clearly explain what field is missing or uncertain.

### AGT-005 - Agent Escalates After Collecting Enough Verification Information

Severity: High

In many calls, the agent collects name, date of birth, spelling, and phone number, then says it cannot proceed and transfers or promises clinic follow-up. The transfer reaches the intentionally dead test line; the failure is the escalation decision, not the dead line.

Examples:

- `appointment_scheduling/call-006`: the agent collects identity and phone information, then says it cannot access the record and routes to support.
- `information_gathering/call-021`: the agent collects identity information, then cannot check insurance and offers transfer.
- `unknown/call-002`: the caller asks for a medication refill, the agent verifies identity, then escalates without resolving the request.

Expected behavior: complete lookup using the available verified fields or explicitly state which field failed. Escalation should be reserved for warranted cases and should preserve the patient's stated task.

### AGT-006 - Agent Loses or Does Not Resolve Medication Refill Intent

Severity: Medium

Some medication-refill calls are consumed by verification and never reach a useful refill workflow. This is distinct from calls where the patient lacks medication details and the agent reasonably routes to staff.

Examples:

- `medication_refill/call-005`: caller asks for a refill; agent verifies, then escalates without collecting medication details.
- `medication_refill/call-009`: agent asks verification questions, misconfirms details, and escalates before resolving the refill.
- `unknown/call-002`: caller asks for a blood-pressure medication refill; the request is not resolved before escalation.

Expected behavior: acknowledge the refill request early, collect medication/pharmacy/urgency details when possible, and pass the request context forward if escalation is required.

### AGT-007 - Agent Does Not Handle Records Request

Severity: Medium

The agent fails to handle a medical-records request as a records workflow.

Example:

- `orthopedic_edge_cases/call-006`: caller says they need records sent to another doctor. The call proceeds through identity verification and escalation without explaining records authorization or routing to records.

Patient-bot note: this transcript later contains patient-bot reasoning text, so it should not be used to judge later call turns. The records request itself is stated clearly before that artifact.

Expected behavior: acknowledge the records request, explain authorization requirements, and route or collect the appropriate information.

### AGT-008 - Agent Does Not Collect Worker's Comp Intake Information

Severity: Medium

The agent acknowledges worker's comp but does not collect worker's comp-specific information such as employer, claim number, insurer, or authorization status.

Examples:

- `orthopedic_edge_cases/call-004`: caller says the ankle injury should go through worker's comp; agent confirms the practice handles it and moves into ordinary scheduling/verification.
- `orthopedic_edge_cases/call-008`: caller repeats the worker's comp context; agent escalates without collecting claim details.

Expected behavior: distinguish worker's comp from ordinary scheduling and collect or route for claim/authorization details.

### AGT-009 - Agent Does Not Apply Minor/Guardian Handling

Severity: High

The agent receives dates of birth indicating the caller/patient is a minor, but does not reliably apply guardian or consent handling.

Examples:

- `orthopedic_edge_cases/call-001`: DOB is February 11, 2010. The agent asks whether the caller is calling for themself only after a phone-number confusion, then asks how it can help and repeats DOB without applying minor-consent logic.
- `orthopedic_edge_cases/call-005`: DOB is February 11, 2010. The agent bypasses verification for demo purposes and books an appointment without consent handling.

Expected behavior: recognize minor age from DOB and follow guardian/consent policy before scheduling or modifying care.

### AGT-010 - Agent Sends Text Confirmation Before Resolving Phone Mismatch

Severity: Medium

The agent says a text confirmation was sent before confirming the patient's correct phone number.

Example:

- `orthopedic_edge_cases/call-005`: agent books an appointment and says it sent a text confirmation. Only afterward does the patient provide `555-684-2190`, while the agent reveals the on-file number is `941-842-0514`.

Expected behavior: verify the destination phone number before sending confirmations.

### AGT-011 - Agent Misreads or Truncates Patient-Provided Data

Severity: Medium

The agent often reads back malformed names, dates, or phone numbers.

Examples:

- `appointment_scheduling/call-006`: caller gives `555-318-4492`; agent later reads back `555-4492`.
- `information_gathering/call-010`: caller gives `555-629-3817`; agent reads back `555-3817` and asks for a ten-digit number.
- `unknown/call-002`: caller gives `7745550467`; agent reads back `774-555-046`.
- `medication_refill/call-007`: caller gives birth year 1963; agent first states 1960, then corrects itself mid-turn.

Expected behavior: preserve exact user-provided values and ask for clarification when uncertain rather than presenting corrupted values as confirmed.

### AGT-012 - Agent Acts on Records After Failed Verification

Severity: High

After a date of birth mismatch or wrong-patient correction, the agent sometimes proceeds to cancel, schedule, or discuss an appointment anyway.

Examples:

- `appointment_scheduling/call-028`: after a DOB mismatch/demo override, agent finds and cancels an appointment.
- `difficult_call_handling/call-001`: after a DOB mismatch/demo override, agent schedules a follow-up.
- `orthopedic_edge_cases/call-005`: after a DOB mismatch/demo override, agent books a new appointment.
- `orthopedic_edge_cases/call-007`: after a DOB mismatch/demo override, agent discloses appointment details.

Expected behavior: do not access, modify, or disclose appointment data unless identity verification has succeeded.

## Patient-Bot Artifacts

The following patient-bot artifacts were observed but were not treated as agent bugs:

- Empty transcripts: `information_gathering/call-006`, `medication_refill/call-003`, `medication_refill/call-004`.
- Patient-bot internal reasoning or persona leakage, such as "let me think about the best way..." or "let me respond...": observed in 15 calls.

These artifacts matter because they reduce scenario coverage and sometimes make later turns unfit as evidence. They do not explain the repeated wrong-patient opening, stale phone-number surfacing, demo override language, or verification-loop failures that occur across clean calls.

## Bug Tracking Appendix

### Bug Key Metrics

| Key | Short Name | Severity | Agent-observable Calls | Primary Clean Evidence Calls |
| --- | --- | --- | ---: | ---: |
| AGT-001 | Wrong-patient "James" opening | High | 66 | 54 |
| AGT-002 | Internal demo override language | High | 10 | 8 |
| AGT-003 | Stale/fabricated phone number | High | 20 | 13 |
| AGT-004 | Repeated verification requests | High | 23 | 16 |
| AGT-005 | Escalates after enough verification | High | 48 | 35 |
| AGT-006 | Medication refill intent unresolved | Medium | 6 | 5 |
| AGT-007 | Records request not handled | Medium | 1 | 1 |
| AGT-008 | Worker's comp intake not collected | Medium | 2 | 2 |
| AGT-009 | Minor/guardian handling missing | High | 2 | 2 |
| AGT-010 | Text sent before phone verification | Medium | 1 | 1 |
| AGT-011 | Misreads/truncates patient data | Medium | 13 | 8 |
| AGT-012 | Acts after failed verification | High | 14 | 11 |

### Call-to-Bug Map

`patient-artifact` means later turns include patient-bot behavior that should not be used as primary evidence unless the agent bug occurred independently.

#### `appointment_scheduling/`

| Call | Agent Bug Keys | Notes |
| --- | --- | --- |
| `call-001` | AGT-001, AGT-003, AGT-004, AGT-005 | patient-artifact |
| `call-006` | AGT-001, AGT-003, AGT-004, AGT-005, AGT-011 |  |
| `call-015` | AGT-001, AGT-005, AGT-011 |  |
| `call-016` | AGT-001, AGT-003, AGT-005 |  |
| `call-017` | AGT-001, AGT-005 |  |
| `call-018` | AGT-001, AGT-004, AGT-011 |  |
| `call-019` | AGT-005 |  |
| `call-020` | AGT-001, AGT-003, AGT-005, AGT-011 | patient-artifact |
| `call-021` | AGT-001, AGT-005 |  |
| `call-022` | AGT-001 | short call |
| `call-023` | AGT-001, AGT-005, AGT-012 |  |
| `call-024` | AGT-001, AGT-004, AGT-005 |  |
| `call-025` | AGT-001, AGT-004, AGT-005 | patient-artifact |
| `call-026` | AGT-001, AGT-005 |  |
| `call-027` | AGT-001, AGT-004, AGT-005 |  |
| `call-028` | AGT-001, AGT-002, AGT-012 |  |
| `call-029` | AGT-001, AGT-005 |  |
| `call-030` | AGT-001, AGT-003, AGT-005 |  |
| `call-031` | AGT-001, AGT-003, AGT-005 | patient-artifact |
| `call-032` | AGT-001, AGT-005, AGT-011 | patient-artifact |
| `call-033` | AGT-001, AGT-003, AGT-005 |  |
| `call-034` | AGT-001 |  |
| `call-035` | AGT-001, AGT-003, AGT-004 |  |
| `call-036` | AGT-001 |  |
| `call-037` | AGT-001, AGT-003, AGT-005 |  |
| `call-038` | none | not reviewed - missing transcript |
| `call-039` | none | not reviewed - missing transcript |
| `call-040` | AGT-001, AGT-004 |  |
| `call-041` | AGT-004, AGT-005 | patient-artifact |
| `call-042` | AGT-001, AGT-004 |  |
| `call-043` | AGT-001, AGT-003, AGT-004, AGT-005, AGT-011 | patient-artifact |

#### `difficult_call_handling/`

| Call | Agent Bug Keys | Notes |
| --- | --- | --- |
| `call-001` | AGT-001, AGT-002, AGT-012 |  |
| `call-002` | AGT-001 | short call |
| `call-003` | AGT-001, AGT-004, AGT-005 |  |
| `call-004` | AGT-001, AGT-005 |  |
| `call-005` | AGT-001, AGT-002, AGT-012 |  |
| `call-006` | AGT-001, AGT-004 |  |

#### `information_gathering/`

| Call | Agent Bug Keys | Notes |
| --- | --- | --- |
| `call-001` | none | not reviewed - missing transcript |
| `call-002` | none | not reviewed - missing transcript |
| `call-003` | none | not reviewed - missing transcript |
| `call-004` | none | not reviewed - missing transcript |
| `call-005` | none | not reviewed - missing transcript |
| `call-006` | none | empty transcript |
| `call-007` | AGT-001, AGT-005 |  |
| `call-008` | AGT-001, AGT-004, AGT-005 |  |
| `call-009` | AGT-002, AGT-005, AGT-012 |  |
| `call-010` | AGT-001 |  |
| `call-011` | AGT-002, AGT-005, AGT-012 |  |
| `call-012` | AGT-005 | caller is James |
| `call-013` | AGT-001, AGT-005 | patient-artifact |
| `call-014` | AGT-002, AGT-012 | patient-artifact |
| `call-015` | AGT-001, AGT-003, AGT-004 |  |
| `call-016` | AGT-001, AGT-004 |  |
| `call-017` | AGT-001, AGT-005 |  |
| `call-018` | AGT-001, AGT-005 |  |
| `call-019` | AGT-001 |  |
| `call-020` | AGT-001 | short call |
| `call-021` | AGT-001, AGT-005 |  |
| `call-022` | AGT-001, AGT-004 |  |
| `call-023` | AGT-001, AGT-005 |  |
| `call-024` | AGT-001 |  |

#### `medication_refill/`

| Call | Agent Bug Keys | Notes |
| --- | --- | --- |
| `call-001` | none | not reviewed - missing transcript |
| `call-002` | none | not reviewed - missing transcript |
| `call-003` | none | empty transcript |
| `call-004` | none | empty transcript |
| `call-005` | AGT-001, AGT-003, AGT-005, AGT-006 |  |
| `call-006` | AGT-002, AGT-005, AGT-012 | patient cannot identify medication; refill-specific failure not counted |
| `call-007` | AGT-001, AGT-003, AGT-004, AGT-006, AGT-011 |  |
| `call-008` | AGT-001, AGT-003, AGT-005, AGT-012 | agent handles refill details but still has identity/phone bugs |
| `call-009` | AGT-001, AGT-005, AGT-006, AGT-011 |  |

#### `orthopedic_edge_cases/`

| Call | Agent Bug Keys | Notes |
| --- | --- | --- |
| `call-001` | AGT-001, AGT-009 |  |
| `call-002` | AGT-001 | emergency handling otherwise appropriate |
| `call-003` | AGT-001, AGT-005 |  |
| `call-004` | AGT-001, AGT-005, AGT-008, AGT-012 | patient-artifact after worker's comp request |
| `call-005` | AGT-002, AGT-003, AGT-009, AGT-010, AGT-012 |  |
| `call-006` | AGT-001, AGT-003, AGT-004, AGT-005, AGT-007, AGT-011 | patient-artifact after records request |
| `call-007` | AGT-002, AGT-012 | caller says they are James |
| `call-008` | AGT-001, AGT-005, AGT-008, AGT-011, AGT-012 |  |

#### `smoke/`

| Call | Agent Bug Keys | Notes |
| --- | --- | --- |
| `call-001` | AGT-001, AGT-003, AGT-005 | patient-artifact |
| `call-002` | AGT-001, AGT-003, AGT-004, AGT-005 |  |
| `call-003` | AGT-001, AGT-003, AGT-004, AGT-005 |  |
| `call-004` | AGT-001 |  |

#### `unknown/`

| Call | Agent Bug Keys | Notes |
| --- | --- | --- |
| `call-001` | AGT-002, AGT-004, AGT-011, AGT-012 | patient-artifact |
| `call-002` | AGT-001, AGT-005, AGT-006, AGT-011 |  |
| `call-003` | AGT-001, AGT-003, AGT-004, AGT-005, AGT-011 | patient-artifact |
| `call-004` | AGT-001, AGT-005 |  |
| `call-005` | AGT-001 |  |
| `call-006` | AGT-001, AGT-005, AGT-006 | patient-artifact |
| `call-007` | AGT-006 | incomplete before resolution |
