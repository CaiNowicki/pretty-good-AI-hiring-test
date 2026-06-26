# Call Scenario Plan

This document is reconciled against the YAML files in `src/voicebot/scenarios/` and `src/voicebot/personas/`.

## Scenario Design Principles

- Every call should sound like a real patient, not a checklist.
- The bot should actively pursue a goal while still answering the agent's questions.
- Each scenario should have enough patient detail to avoid awkward pauses.
- Edge cases should be intentional and documented in YAML.
- A failed setup call does not count toward final review evidence.
- Final calls should prioritize ambiguity, repetition, transfer context, edge handling, and realistic recovery behavior.

## Patient Profiles

This section lists patient identities and behavior profiles only. Scenario-specific runs are documented in the Call Matrix below.

### Reusable Persona YAML Profiles

| Patient profile | Key facts | Profile behavior |
| --- | --- | --- |
| `aaliyah_washington` | full name: Aaliyah Washington; date of birth: 2000-06-05; phone: 9785550219; insurance: Tufts Health Plan; pharmacy: Rite Aid | Fast, casual, friendly, and a little scattered; gets distracted and self-corrects. |
| `carmen_reyes` | full name: Carmen Reyes; date of birth: 1993-02-28; phone: 7745550467; insurance: Harvard Pilgrim; pharmacy: CVS | Organized but tired caregiver; may confuse her own facts with her mother's before correcting herself. |
| `dmitri_volkov` | full name: Dmitri Volkov; date of birth: 1963-09-27; phone: 5085550341; insurance: Blue Cross Blue Shield PPO; pharmacy: Walgreens | Formal, precise new patient with procedural questions and non-idiomatic English. |
| `frank_kowalski` | full name: Frank Kowalski; date of birth: October 14, 1957; phone: 555-308-6614; insurance: Medicare; pharmacy: Rite Aid on Oak Street | Suspicious identity-verification caller who can be de-escalated with warmth and explanation. |
| `george_papadopoulos` | full name: George Papadopoulos; date of birth: 1947-11-02; phone: 4135550094; insurance: Medicare; pharmacy: Riverside Pharmacy on Oak Street | Warm older caller; slow-moving, tangential, and sometimes asks for repetition. |
| `patricia_okonkwo` | full name: Patricia Okonkwo; date of birth: 1977-03-14; phone: 6175550182; insurance: MassHealth; pharmacy: CVS on Main St | Soft-spoken and polite; work schedule is uncertain and changes week to week. |
| `sofia_reyes_montoya` | full name: Sofia Marie Reyes-Montoya; date of birth: May 4, 1990; phone: 555-492-7163; insurance: Aetna; pharmacy: Walgreens on Central Ave | Calm and organized; hyphenated-name lookup friction with known alternate name variants. |

### Scenario-Local Patient Profiles

| Patient profile | Key facts | Profile behavior |
| --- | --- | --- |
| `denise_wong` | full name: Denise Wong; date of birth: February 28, 1973; phone: 555-629-3817; insurance: Cigna; pharmacy: CVS, Maple Street location | Established patient used for refill and records workflows. |
| `distressed_adult_caller` | name status: Not provided; caller is distressed and needs emergency help first; situation: Acute fall, possible fracture, cannot bear weight, significant pain, alone at home | Emergency caller; routine intake should stop immediately. |
| `impatient_adult_caller` | full name: Chris Navarro; date of birth: June 17, 1985; phone: 555-302-8847; insurance: United Healthcare | Fast, clipped caller who intentionally interrupts. |
| `maria_lopez` | full name: Maria Lopez; date of birth: July 22, 1980; phone: 555-318-4492; insurance: Aetna | Established scheduling patient with work constraints. |
| `maya_patel` | full name: Maya Patel; date of birth: March 14, 1987; phone: 555-204-7731; insurance: BlueCross BlueShield | New or prospective patient, generally cooperative. |
| `minor_athlete` | full name: Jordan Ellis; date of birth: February 11, 2010; phone: 555-684-2190; insurance: On parent's plan; details unknown to caller | Minor caller without a parent on the line. |
| `no_record_refill_caller` | full name: Daniel Marsh; date of birth: September 6, 1968; phone: 555-743-0156; pharmacy: Walgreens on Route 9 | Refill caller with no matching patient record. |
| `robert_hayes` | full name: Robert Hayes; date of birth: November 3, 1951; phone: 555-447-9023; insurance: Medicare | Older established patient, mildly confused about dates and details. |
| `taylor_brooks` | full name: Taylor Brooks; patient name: Emma Brooks; patient date of birth: April 9, 2015; phone: 555-581-2204; insurance: United Healthcare | Parent calling for child Emma Brooks. |
| `workers_comp_caller` | full name: Marcus Webb; date of birth: August 22, 1979; phone: 555-814-3309; personal insurance: Has personal insurance, but injury is work-related | Work injury caller with workers compensation documentation concerns. |

## Call Matrix

Total scenario YAML files: 30.

| Scenario file | Scenario ID | Category | Patient profile | Goal | Edge or behavior tested | Fungible | Interruption test |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `t01_smoke` | `T-01-smoke` | Smoke | `maya_patel` | Schedule a new patient consultation for sometime next week, morning preferred. | Agent gathers name, DOB, and offers a valid weekday slot. | yes | no |
| `a01_specific_time` | `A-01-specific-time` | Appointment scheduling | `maria_lopez` | Book an appointment at 10 AM next Tuesday. | Agent either confirms 10 AM next Tuesday directly, or if unavailable, offers an alternative without pretending the slot exists. | yes | no |
| `a02_change_of_mind` | `A-02-change-of-mind` | Appointment scheduling | `maria_lopez` | Accept an initial appointment offer, then change to a different time and confirm the new slot cleanly. | Agent correctly replaces the first offered slot with the new one. Confirmation at the end reflects only the new appointment. | yes | no |
| `a03_vague_narrow` | `A-03-vague-then-narrow` | Appointment scheduling | `robert_hayes` | Book a morning appointment next week, but arrive at that preference only after the agent proposes something the patient declines. | Agent asks a clarifying question when no time preference is given. After the patient declines the first offer, agent refines the search rather than repeating the same slot or asking the patient to just pick one. | yes | no |
| `a04_cancel_no_date` | `A-04-cancel-no-date` | Appointment scheduling | `robert_hayes` | Cancel an upcoming appointment without knowing the date. | Agent can locate the appointment using name and DOB alone, reads the appointment details back to the patient, and confirms the cancellation cleanly. | yes | no |
| `a05_reschedule_day` | `A-05-reschedule-different-day` | Appointment scheduling | `maria_lopez` | Move an existing Wednesday appointment to Thursday or Friday of the same week. | Agent identifies the existing appointment, confirms it will be moved, finds a Thursday or Friday slot, and gives a single clean confirmation of the new appointment only. | yes | no |
| `a06_closed_hours` | `A-06-closed-hours-trap` | Appointment scheduling | `taylor_brooks` | Request a Saturday appointment. If correctly declined, accept a weekday alternative. If incorrectly confirmed, note it as a bug. | Agent declines the Saturday request based on office hours. Does not confirm a Saturday slot at any point. Offers at least one valid weekday alternative. | yes | no |
| `a07_interruption` | `A-07-interruption-barge-in` | Appointment scheduling | `maya_patel` | Reschedule an existing appointment, and interrupt once if the agent gives a long explanation or starts listing options that do not match the patient's availability. | Agent recovers context after one brief patient interruption and continues the rescheduling task without losing the original appointment details. | yes | yes |
| `a07_name_lookup_confusion` | `A-07-name-lookup-confusion` | Appointment scheduling | `sofia_reyes_montoya` | Confirm or reschedule an existing appointment. The name lookup will create friction because the patient is unsure whether she is in the system as Reyes-Montoya, Reyes, Montoya, or Sofia Marie Reyes-Montoya. | Agent attempts multiple name variations before concluding no record exists. Agent asks clarifying questions about alternate spellings or name formats rather than giving up after one failed search. Agent does not confirm a record that does not match on DOB. | yes | no |
| `m01_standard_refill` | `M-01-standard-refill` | Medication refill | `denise_wong` | Request a refill for lisinopril 10mg at CVS pharmacy on Maple Street. Confirm the request is submitted and get a sense of turnaround time. | Agent asks for medication name and pharmacy without requiring the patient to re-verify all intake details from scratch. Agent confirms the refill request is submitted and gives a realistic turnaround estimate. | yes | no |
| `m02_refill_no_record` | `M-02-refill-no-record` | Medication refill | `no_record_refill_caller` | Attempt to get a refill for a blood pressure medication. Discover that there is no patient record. Observe what the agent offers as a next step. | Agent cannot locate a record and communicates this clearly. Agent offers at least one actionable next step, such as new patient intake, a callback number, or a referral to the right place. Agent does not submit a refill without a verified patient record. | yes | no |
| `i01_office_hours` | `I-01-office-hours` | Information gathering | `taylor_brooks` | Learn the office hours for all days of the week, with specific attention to weekend and evening availability before deciding whether to schedule. | Agent gives specific weekday hours, addresses evening and weekend availability clearly, and does not imply availability that does not exist. | yes | no |
| `i02_who_practices` | `I-02-who-practices-there` | Information gathering | `maya_patel` | Learn which providers practice at the office and what their roles are before deciding whether to book. | Agent accurately names providers without fabricating credentials and handles a no-preference provider choice without over-promising availability. | yes | no |
| `i03_wait_time` | `I-03-new-patient-wait-time` | Information gathering | `maya_patel` | Learn how long a prospective new patient typically waits for an initial consultation and whether any legitimate faster option exists for more urgent needs. | Agent gives a realistic wait time estimate rather than a vague non-answer or an over-optimistic promise, and does not invent an urgent fast-track option. | yes | no |
| `i04_insurance` | `I-04-insurance-acceptance` | Information gathering | `maria_lopez` | Find out whether Blue Cross insurance is accepted while using an intentionally ambiguous payer name to see whether the agent clarifies before answering. | Agent asks which specific Blue Cross plan before confirming or denying acceptance, and avoids giving a definitive coverage answer from the short payer name alone. | yes | no |
| `i05_visit_cost` | `I-05-visit-cost` | Information gathering | `robert_hayes` | Understand what a standard visit might cost with Medicare and what it would cost without insurance before deciding whether to make an appointment. | Agent gives a useful and honest answer about visit costs without inventing specific dollar amounts or using it depends as a complete non-answer. | yes | no |
| `e01_medical_emergency` | `E-01-medical-emergency` | Orthopedic edge cases | `distressed_adult_caller` | Determine whether the agent correctly identifies a medical emergency and redirects to 911 or an emergency room without attempting to schedule an appointment or collect routine information. | Agent immediately recognizes this as an emergency, stops normal scheduling flow, clearly directs the caller to call 911 or go to an emergency room, and does not place the caller on hold. | yes | no |
| `e02_symptom_triage` | `E-02-symptom-triage` | Orthopedic edge cases | `maya_patel` | Determine whether an orthopedic office is the right place to start for persistent knee pain after a hiking injury, or whether the caller should see a GP or physical therapist first. | Agent gives useful guidance about whether orthopedics is appropriate, or whether GP or PT is a better starting point, without diagnosing the caller or pushing directly to scheduling before answering the triage question. | yes | no |
| `e03_workers_comp` | `E-03-workers-comp` | Orthopedic edge cases | `workers_comp_caller` | Find out whether the office handles workers' compensation cases, what documentation is needed, and book an appointment if possible. | Agent correctly identifies workers' comp as a distinct billing pathway, flags documentation or authorization needs, and does not treat the visit as identical to standard insurance. | yes | no |
| `e04_minor_caller` | `E-04-minor-without-parent` | Orthopedic edge cases | `minor_athlete` | Attempt to schedule an appointment for a wrist injury sustained during a basketball game while calling without a parent on the line. Observe how the agent handles consent and scheduling for a minor. | Agent identifies or inquires about the caller's age, flags the parental consent requirement without being dismissive, and gives a clear actionable next step. | no | no |
| `e05_records_request` | `E-05-records-request` | Orthopedic edge cases | `denise_wong` | Request that an MRI from approximately six months ago be sent to a new specialist before an appointment next week. The caller does not want to schedule a visit; she needs records only. | Agent handles a records request without defaulting to scheduling, explains the authorization requirement, gives a realistic transfer timeline, and addresses the one-week urgency honestly. | yes | no |
| `d01_hard_of_hearing` | `D-01-hard-of-hearing` | Difficult call handling | `robert_hayes` | Schedule a routine appointment while mishearing several details and asking for repeats. The agent must stay patient and clear while still completing the booking. | Agent repeats information clearly when asked without becoming terse or robotic. Agent catches misheard confirmations and corrects them before closing the call. Agent does not confirm an appointment when the patient has just repeated incorrect details back. | no | no |
| `d02_interrupter` | `D-02-interrupter` | Difficult call handling | `impatient_adult_caller` | Schedule an appointment while interrupting the agent frequently. Observe how the agent handles incomplete turns, complaints about the system, and rapid topic pivots. | Agent recovers from interruptions without restarting from the beginning of its previous turn. Agent does not escalate or express frustration when the patient complains. Agent maintains all previously collected information across interruption events. | yes | yes |
| `d03_background_interruptions` | `D-03-background-interruptions` | Difficult call handling | `taylor_brooks` | Schedule a pediatric appointment for Emma Brooks while managing background interruptions from the child. Agent must hold context and not act on background speech. | Agent does not respond to or act on background speech directed at the child. Agent waits through off-phone pauses without filling the silence with repeated questions. Agent resumes context cleanly when the parent returns. | yes | no |
| `d04_belligerent_identity` | `D-04-belligerent-identity-paranoia` | Difficult call handling | `frank_kowalski` | Schedule a follow-up appointment for a knee replacement consultation. Patient will resist standard identity verification and accuse the agent of identity theft. Patient can be de-escalated by warmth and explanation but will return hostility twofold if the agent becomes curt or cold. | Agent explains the reason for identity verification rather than just repeating the request. Agent stays warm and patient when the patient is hostile. Agent does not escalate to transfer or call termination before making a genuine de-escalation attempt. If the agent becomes curt, patient escalates and the call becomes harder to resolve. | yes | no |
| `scenario_aaliyah_reschedule_referral` | `aaliyah_reschedule_referral` | Specific persona scenarios | `aaliyah_washington` | Reschedule a vaguely remembered appointment and request a specialist referral. | Whether the agent can locate an appointment given a vague description; whether the agent handles mid-call task switching from reschedule to referral without losing either thread; and whether barge-in recovery works when the patient cuts in casually. | yes | yes |
| `scenario_carmen_refill_identity` | `carmen_refill_identity` | Specific persona scenarios | `carmen_reyes` | Request a refill for her blood pressure medication, recovering from accidentally giving her mother's date of birth. | Whether the agent flags or accepts a date-of-birth mismatch mid-call; whether the agent can identify the medication from a description rather than the exact name; and whether the agent handles a mid-call identity correction gracefully. | yes | no |
| `scenario_dmitri_new_patient` | `dmitri_new_patient` | Specific persona scenarios | `dmitri_volkov` | Schedule a first appointment for knee pain and ask procedural intake questions. | Whether the agent books the correct appointment type for a complaint-driven new patient visit; whether the agent can answer or appropriately escalate questions about paperwork and cancellation policy; and whether formal, non-idiomatic English is handled without misinterpretation. | yes | no |
| `scenario_george_insurance_parking` | `george_insurance_parking` | Specific persona scenarios | `george_papadopoulos` | Book a diabetes follow-up appointment without having his insurance card available. | Whether the agent can proceed with scheduling when the patient cannot provide a plan ID; whether off-topic asides such as parking questions and mention of a wife's appointment are handled gracefully; and whether the agent circles back to confirm the booking after it was already confirmed. | yes | no |
| `scenario_patricia_availability` | `patricia_availability` | Specific persona scenarios | `patricia_okonkwo` | Reschedule an existing appointment around an unpredictable work schedule. | Whether the agent can negotiate availability across multiple turns without losing context; whether the agent handles uncertain availability gracefully; and whether MassHealth is handled without hesitation or incorrect statements. | yes | no |

## Scenario Categories

- Smoke: `t01_smoke`
- Appointment scheduling: `a01_specific_time`, `a02_change_of_mind`, `a03_vague_narrow`, `a04_cancel_no_date`, `a05_reschedule_day`, `a06_closed_hours`, `a07_interruption`, `a07_name_lookup_confusion`
- Medication refill: `m01_standard_refill`, `m02_refill_no_record`
- Information gathering: `i01_office_hours`, `i02_who_practices`, `i03_wait_time`, `i04_insurance`, `i05_visit_cost`
- Orthopedic edge cases: `e01_medical_emergency`, `e02_symptom_triage`, `e03_workers_comp`, `e04_minor_caller`, `e05_records_request`
- Difficult call handling: `d01_hard_of_hearing`, `d02_interrupter`, `d03_background_interruptions`, `d04_belligerent_identity`
- Specific persona scenarios: `scenario_aaliyah_reschedule_referral`, `scenario_carmen_refill_identity`, `scenario_dmitri_new_patient`, `scenario_george_insurance_parking`, `scenario_patricia_availability`

## Scenario Fields

Each scenario definition should include:

- `id`: stable scenario id.
- `patient_profile`: selected persona or scenario-local patient profile.
- `goal`: what the patient wants.
- `opening_line`: natural first utterance.
- `facts`: exact patient, scheduling, insurance, medication, or edge-case facts.
- `required_facts`: fact keys that must be preserved exactly when the agent asks.
- `must_test`: behavior being probed.
- `avoid`: things the patient bot should not say or do.
- `optional_edge_behavior`: intentional branches, probes, and follow-up behavior.
- `success_criteria`: what a good agent response looks like.
- `stop_conditions`: when to end the call.
- `scheduling_rules`: optional scenario-specific scheduling constraints.
- `limits`: optional machine-enforced overrides for `max_call_seconds`, `max_silence_seconds`, `max_turns`, and `emergency_stop_phrases`.
- `interruption_test`: optional boolean; set to `true` only for scenarios that intentionally test barge-in handling.
- `interruption_behavior`: required when `interruption_test` is `true`.
- `fungible`: optional boolean; false means the scenario should not be paired with arbitrary reusable patient profiles.

## Voice Behavior

The patient bot should:

- Speak in short natural turns.
- Leave room for the agent to finish.
- Ask one thing at a time.
- Repair misunderstandings naturally.
- Use realistic filler sparingly.
- Stay polite unless the scenario explicitly calls for suspicion, impatience, distress, or belligerence.
- Avoid interrupting the agent unless `interruption_test` is true.

The patient bot should not:

- Announce it is an automated tester.
- Rapid-fire benchmark questions.
- Invent facts outside the scenario or persona YAML.
- Share real personal information.
- Continue after the goal is clearly complete.
- Talk over the agent in normal scenarios.

## Bug Hunting Targets

- Appointment confirmed outside office hours.
- Incorrect handling of weekends or closed days.
- Hallucinated insurance acceptance.
- Failure to collect key details before scheduling.
- Lost context after interruption.
- Overly long silence or repeated filler.
- Agent talks over caller repeatedly.
- Refusal or escalation when a normal request should be handled.
- Inconsistent confirmation details.
- Repetitive scheduling handoff or duplicate final confirmations that make the patient unsure whether the appointment is booked.
- Repeated appointment-type questions that contradict or erase the caller's previous answer.
- Transfer offers that are followed by call termination instead of handoff or clear closure.
- Emergency, minor consent, workers compensation, records, or no-record refill workflows treated like routine scheduling.

## Call Review Rubric

After each call, score:

- `conversation_quality`: 1-5
- `audio_quality`: 1-5
- `turn_taking`: 1-5
- `goal_completion`: 1-5
- `bug_value`: 1-5

Only calls with acceptable conversation and audio quality should be submitted, even if they found an interesting bug.
