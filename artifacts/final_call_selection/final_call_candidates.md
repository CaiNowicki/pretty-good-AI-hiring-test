# Final Call Candidate Review

Generated: 2026-06-26T14:27:03.205+00:00

Selection policy:
- HARD GATE: calls must be at least 60 seconds long, with a non-empty recording and speaker-labeled transcript.
- Ranking favors judgeability: longer calls, more turns, speaker balance, and transcript coherence.
- Ranking does not reward success, failure, or whether either bot looks good.
- Automated first pass flags policy, factual, flow, and voice-quality issues for reviewer triage.
- Manual listening/review is still required before a call is included in the final package.

Discovered calls: 75
Eligible after hard gates and severe sensibility checks: 61
Rejected by hard gate: 14

## Automated First Pass

Policy: 2 | Factual: 59 | Flow: 53 | Voice quality: 24

## Top 10 Review Queue

| Rank | Call | Type | Duration | Turns | Score | Review | Issues | Flags |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| 1 | `orthopedic_edge_cases-call-005` | `orthopedic_edge_cases` | 240s | 38 | 93.3 | pass | 1 | none |
| 2 | `medication_refill-call-007` | `medication_refill` | 197s | 39 | 86.7 | pass | 2 | none |
| 3 | `appointment_scheduling-call-020` | `appointment_scheduling` | 199s | 33 | 85.8 | pass | 2 | none |
| 4 | `appointment_scheduling-call-025` | `appointment_scheduling` | 162s | 36 | 84.0 | pass | 2 | none |
| 5 | `appointment_scheduling-call-031` | `appointment_scheduling` | 185s | 34 | 83.4 | pass | 2 | none |
| 6 | `information_gathering-call-021` | `information_gathering` | 193s | 30 | 83.1 | pass | 2 | none |
| 7 | `unknown-call-002` | `unknown` | 162s | 31 | 79.7 | pass | 2 | none |
| 8 | `unknown-call-001` | `unknown` | 166s | 32 | 78.8 | pass | 0 | none |
| 9 | `orthopedic_edge_cases-call-004` | `orthopedic_edge_cases` | 145s | 33 | 78.6 | pass | 2 | none |
| 10 | `smoke-call-002` | `smoke` | 158s | 31 | 76.5 | pass | 2 | none |

## Manual Review Checklist

- Listen to the recording and confirm the transcript matches both speakers.
- Check every automated issue flag against the recording before promoting it.
- Confirm the dialogue stays sensible through the end, not just near the bug evidence.
- Exclude calls where patient-bot glitches create the apparent issue.
- Exclude calls where the agent-bot outcome is unjudgeable because the call setup degraded.
- Prefer calls that expose decision points, recovery behavior, clarifications, or safety handling.

## Automated Issues In Selected Calls

| Call | Category | Severity | Source | Finding | Evidence |
| --- | --- | --- | --- | --- | --- |
| `orthopedic_edge_cases-call-005` | policy | medium | agent_bot | Minor or guardian context may not have been acknowledged by the agent. | PGAI Agent: This call may be recorded for quality and training purposes. Para español, oprima el dos. |
| `medication_refill-call-007` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...t: I’m calling to request a refill on one of my medications, but I think you may have the wrong patient. The caller is Dmitri Volkov. PGAI Agent: Can you please provide your full name and date... |
| `medication_refill-call-007` | factual | high | agent_bot | Agent may have confirmed an incorrect phone number or stale record. | ...PGAI Agent: Is that correct? Patient Bot: My name and date of birth are correct, but that phone number is not mine. My phone number is 5085550341. PGAI Agent: No problem. PGAI Agent: Thanks for clarifying... |
| `appointment_scheduling-call-020` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...tty Good AI. Am I speaking with James? Patient Bot: This is Maria Lopez. You may have the wrong patient if you were expecting James. I’ll wait for your next question. PGAI Agent: Thanks for cla... |
| `appointment_scheduling-call-020` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...you to a representative. Please wait PGAI Agent: Hello, you've reached the Pretty Good AI test line. Goodbye. Patient Bot: Okay, thank you. Goodbye. |
| `appointment_scheduling-call-025` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...AI Agent: Am I speaking with James? Patient Bot: This is Maria Lopez, so you may have the wrong patient. Hi, I'd like to make an appointment for next Tuesday at 10 AM. PGAI Agent: Thanks for cl... |
| `appointment_scheduling-call-025` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...esentative. PGAI Agent: Please wait. PGAI Agent: Hello, you've reached the Pretty Good AI test line. Goodbye. Patient Bot: Goodbye. |
| `appointment_scheduling-call-031` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...etty Good AI. PGAI Agent: Am I speaking with James? Patient Bot: I think you may have the wrong patient—the caller is Robert Hayes. Yes, hello. I need to see the doctor sometime next week if po... |
| `appointment_scheduling-call-031` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ..., let me think about the best way to PGAI Agent: Hello, you've reached the Pretty Good AI Test Line. Goodbye. Patient Bot: Goodbye. |
| `information_gathering-call-021` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...Good AI. Am I speaking with James? Patient Bot: This is Dmitri Volkov. You might have the wrong patient if you’re looking for James. I wanted to check if you take Blue Cross insurance. PGAI Age... |
| `information_gathering-call-021` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...ou to a representative, please wait. PGAI Agent: Hello, you've reached the Pretty Good AI test line. |
| `unknown-call-002` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...ty Good AI. Am I speaking with James? Patient Bot: This is Carmen Reyes. You may have the wrong patient if you’re expecting James. Hi, I need to get a refill on my blood pressure medication. Th... |
| `unknown-call-002` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...d a refill on my blood pressure medication. PGAI Agent: You've reached the Pretty Good AI Test Line. Goodbye. Patient Bot: Okay, goodbye. |
| `orthopedic_edge_cases-call-004` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...etty Good AI. PGAI Agent: Am I speaking with James? Patient Bot: I think you may have the wrong patient—this is Marcus Webb. Hi, I hurt my ankle at work a couple days ago and I need to come in.... |
| `orthopedic_edge_cases-call-004` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...please wait. Patient Bot: Okay, I’ll PGAI Agent: Hello, you've reached the Pretty Good AI test line. Goodbye. Patient Bot: Goodbye. |
| `smoke-call-002` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...etty Good AI. Am I speaking with James? Patient Bot: This is Maya Patel. You may have the wrong patient if you were expecting James. Hi, I'm hoping to make an appointment. I'm a new patient. PG... |
| `smoke-call-002` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...pport team. PGAI Agent: Please wait. PGAI Agent: Hello, you've reached the Pretty Good AI test line. Goodbye. Patient Bot: Goodbye. |

## Near Misses

| Call | Type | Duration | Turns | Score | Review | Issues | Flags |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| `appointment_scheduling-call-006` | `appointment_scheduling` | 176s | 34 | 82.3 | pass | 2 | none |
| `appointment_scheduling-call-023` | `appointment_scheduling` | 170s | 33 | 79.8 | pass | 1 | none |
| `appointment_scheduling-call-041` | `appointment_scheduling` | 184s | 31 | 78.9 | pass | 1 | none |
| `appointment_scheduling-call-030` | `appointment_scheduling` | 159s | 32 | 76.9 | pass | 2 | none |
| `orthopedic_edge_cases-call-006` | `orthopedic_edge_cases` | 160s | 26 | 74.7 | pass | 2 | none |
| `appointment_scheduling-call-017` | `appointment_scheduling` | 150s | 29 | 74.0 | pass | 2 | none |
| `appointment_scheduling-call-015` | `appointment_scheduling` | 158s | 26 | 73.4 | pass | 2 | none |
| `information_gathering-call-019` | `information_gathering` | 152s | 30 | 73.3 | pass | 1 | none |
| `appointment_scheduling-call-032` | `appointment_scheduling` | 172s | 24 | 73.3 | pass | 2 | none |
| `appointment_scheduling-call-018` | `appointment_scheduling` | 163s | 36 | 72.5 | review | 1 | repeated_utterance_count_5 |

## Hard-Gate Rejections

- `appointment_scheduling-call-022`: duration_below_60s
- `appointment_scheduling-call-038`: duration_unknown; recording_missing; transcript_missing; no_speaker_labeled_turns
- `appointment_scheduling-call-039`: duration_unknown; recording_missing; transcript_missing; no_speaker_labeled_turns
- `difficult_call_handling-call-002`: duration_below_60s
- `information_gathering-call-001`: duration_unknown; recording_missing; transcript_missing; no_speaker_labeled_turns
- `information_gathering-call-002`: duration_unknown; recording_missing; transcript_missing; no_speaker_labeled_turns
- `information_gathering-call-003`: duration_unknown; recording_missing; transcript_missing; no_speaker_labeled_turns
- `information_gathering-call-004`: duration_unknown; recording_missing; transcript_missing; no_speaker_labeled_turns
- `information_gathering-call-005`: duration_unknown; recording_missing; transcript_missing; no_speaker_labeled_turns
- `information_gathering-call-006`: duration_unknown; transcript_empty; no_speaker_labeled_turns
- `medication_refill-call-001`: duration_unknown; recording_missing; transcript_missing; no_speaker_labeled_turns
- `medication_refill-call-002`: duration_unknown; recording_missing; transcript_missing; no_speaker_labeled_turns
- `medication_refill-call-003`: duration_unknown; transcript_empty; no_speaker_labeled_turns
- `medication_refill-call-004`: duration_unknown; transcript_empty; no_speaker_labeled_turns
