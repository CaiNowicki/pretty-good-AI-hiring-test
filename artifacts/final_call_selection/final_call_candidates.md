# Final Call Candidate Review

Generated: 2026-06-26T16:59:57.006+00:00

Selection policy:
- HARD GATE: calls must be at least 60 seconds long, with a non-empty recording and speaker-labeled transcript.
- Ranking favors judgeability: longer calls, more turns, speaker balance, and transcript coherence.
- Ranking does not reward success, failure, or whether either bot looks good.
- Automated first pass flags policy, factual, flow, and voice-quality issues for reviewer triage.
- Manual listening/review is still required before a call is included in the final package.

Discovered calls: 80
Eligible after hard gates and severe sensibility checks: 74
Rejected by hard gate: 6

## Automated First Pass

Policy: 2 | Factual: 72 | Flow: 57 | Voice quality: 7

## Top 10 Review Queue

| Rank | Call | Type | Duration | Turns | Score | Review | Issues | Flags |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| 1 | `medication_refill-call-007` | `medication_refill` | 197s | 39 | 100.2 | pass | 2 | none |
| 2 | `information_gathering-call-021` | `information_gathering` | 193s | 30 | 98.1 | pass | 2 | none |
| 3 | `orthopedic_edge_cases-call-005` | `orthopedic_edge_cases` | 240s | 38 | 96.0 | pass | 1 | none |
| 4 | `appointment_scheduling-call-023` | `appointment_scheduling` | 170s | 33 | 97.3 | pass | 2 | none |
| 5 | `appointment_scheduling-call-020` | `appointment_scheduling` | 199s | 33 | 96.8 | pass | 2 | none |
| 6 | `appointment_scheduling-call-043` | `appointment_scheduling` | 195s | 37 | 94.8 | review | 3 | Patient Bot repeated 2 times: My date of birth is July 22, 1980.; Patient Bot repeated 2 times: 555-318-4492; PGAI Agent repeated 2 times: Please provide your date of birth. |
| 7 | `medication_refill-call-008` | `medication_refill` | 190s | 36 | 93.3 | pass | 1 | none |
| 8 | `orthopedic_edge_cases-call-006` | `orthopedic_edge_cases` | 160s | 26 | 85.7 | pass | 2 | none |
| 9 | `unknown-call-002` | `unknown` | 162s | 31 | 84.7 | pass | 2 | none |
| 10 | `smoke-call-002` | `smoke` | 158s | 31 | 84.5 | pass | 2 | none |

## Manual Review Checklist

- Listen to the recording and confirm the transcript matches both speakers.
- Check every automated issue flag against the recording before promoting it.
- Confirm the dialogue stays sensible through the end, not just near the bug evidence.
- Exclude calls where patient-bot glitches create the apparent issue.
- Exclude calls where the agent-bot outcome is unjudgeable because the call setup degraded.
- Prefer calls that expose decision points, recovery behavior, clarifications, or safety handling.

## Automated Issues In Selected Calls

| Type of Error | Selected Calls |
| --- | ---: |
| Agent may have assumed or surfaced the wrong patient identity. | 9 |
| Agent escalated or transferred the call instead of resolving it in-bot. | 7 |
| Agent may have confirmed an incorrect phone number or stale record. | 2 |
| Minor or guardian context may not have been acknowledged by the agent. | 1 |
| Possible verification loop detected from repeated verification exchanges. | 1 |

## Selected Call Findings

| Call | Category | Severity | Source | Finding | Evidence |
| --- | --- | --- | --- | --- | --- |
| `medication_refill-call-007` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...t: I’m calling to request a refill on one of my medications, but I think you may have the wrong patient. The caller is Dmitri Volkov. PGAI Agent: Can you please provide your full name and date... |
| `medication_refill-call-007` | factual | high | agent_bot | Agent may have confirmed an incorrect phone number or stale record. | ...PGAI Agent: Is that correct? Patient Bot: My name and date of birth are correct, but that phone number is not mine. My phone number is 5085550341. PGAI Agent: No problem. PGAI Agent: Thanks for clarifying... |
| `information_gathering-call-021` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...Good AI. Am I speaking with James? Patient Bot: This is Dmitri Volkov. You might have the wrong patient if you’re looking for James. I wanted to check if you take Blue Cross insurance. PGAI Age... |
| `information_gathering-call-021` | flow | medium | agent_bot | Agent escalated or transferred the call instead of resolving it in-bot. | ...Date of birth as September 27, 1930. I can't check insurance details right now, but I can connect you to our patient support team for help. Would you like me to transfer you? Are you still th... |
| `orthopedic_edge_cases-call-005` | policy | medium | agent_bot | Minor or guardian context may not have been acknowledged by the agent. | No direct transcript line: this issue is inferred from minor or guardian context and the absence of agent acknowledgement. |
| `appointment_scheduling-call-023` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...AI. Am I speaking with James? Patient Bot: This is Sofia Reyes-Montoya. You may have the wrong patient. Please go ahead when you’re ready. PGAI Agent: Please provide the full name and date of... |
| `appointment_scheduling-call-023` | flow | medium | agent_bot | Agent escalated or transferred the call instead of resolving it in-bot. | ...nfirm the phone number you have on file with us? This will help me look up your record. I can't proceed further right now, but I can make sure our clinic support team follows up with you. Anja, Please... |
| `appointment_scheduling-call-020` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...tty Good AI. Am I speaking with James? Patient Bot: This is Maria Lopez. You may have the wrong patient if you were expecting James. I’ll wait for your next question. PGAI Agent: Thanks for cla... |
| `appointment_scheduling-call-020` | flow | medium | agent_bot | Agent escalated or transferred the call instead of resolving it in-bot. | ...2, 1980, is that correct? I can't put these further right now, I can make sure our clinic support team follows up with you. Please hold while I connect you to our patient support team. Connect... |
| `appointment_scheduling-call-043` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...tty Good AI. Am I speaking with James? Patient Bot: This is Maria Lopez. You may have the wrong patient. Hi, I'd like to make an appointment for next Tuesday at 10 AM. PGAI Agent: Please provid... |
| `appointment_scheduling-call-043` | factual | high | agent_bot | Agent may have confirmed an incorrect phone number or stale record. | ...PGAI Agent: Is that correct? Patient Bot: My name and date of birth are correct, but that phone number is not mine. My phone number is 555-318-4492. PGAI Agent: Please provide your date of birth. Patient... |
| `appointment_scheduling-call-043` | flow | medium | agent_bot | Agent escalated or transferred the call instead of resolving it in-bot. | ...ok up your record now. One moment. I'm unable to verify your information right now. I can connect you to our patient support team for help. Would you like me to transfer you? Connecting you t... |
| `appointment_scheduling-call-043` | review_flag | medium | conversation | Possible verification loop detected from repeated verification exchanges. | Patient Bot repeated 2 times: My date of birth is July 22, 1980.; Patient Bot repeated 2 times: 555-318-4492; PGAI Agent repeated 2 times: Please provide your date of birth. |
| `medication_refill-call-008` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...t: Hi, I’m calling to request a refill on one of my medications. I think you may have the wrong patient though; the caller is Denise Wong. PGAI Agent: Can you please provide your date of birth?... |
| `orthopedic_edge_cases-call-006` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ..., part of Pretty Good AI. Am I speaking with James? Patient Bot: I think you may have the wrong patient. The caller is Denise Wong. Hi, I don't need an appointment. I actually need to get some... |
| `orthopedic_edge_cases-call-006` | flow | medium | agent_bot | Agent escalated or transferred the call instead of resolving it in-bot. | ...h February 1973, and your phone number as 941-842-0514. Let me look up your record now. I can't proceed further right now, but I can make sure our clinic support team follows up with you. Please hold w... |
| `unknown-call-002` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...ty Good AI. Am I speaking with James? Patient Bot: This is Carmen Reyes. You may have the wrong patient if you’re expecting James. Hi, I need to get a refill on my blood pressure medication. Th... |
| `unknown-call-002` | flow | medium | agent_bot | Agent escalated or transferred the call instead of resolving it in-bot. | ...e number as 774-555-046. and your date of birth? As February 28, 1993, Is that correct? I can't proceed further right now. Make sure our clinic support team follows up with you. Please hold while I con... |
| `smoke-call-002` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...etty Good AI. Am I speaking with James? Patient Bot: This is Maya Patel. You may have the wrong patient if you were expecting James. Hi, I'm hoping to make an appointment. I'm a new patient. PG... |
| `smoke-call-002` | flow | medium | agent_bot | Agent escalated or transferred the call instead of resolving it in-bot. | ...zero five one four. Újabbak. And your date of birth is March 14, 1987. Is that correct? I can't proceed further right now, but I can make sure our clinic support team follows was up a few. Please hold... |

## Near Misses

| Call | Type | Duration | Turns | Score | Review | Issues | Flags |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| `appointment_scheduling-call-031` | `appointment_scheduling` | 185s | 34 | 92.9 | pass | 2 | none |
| `appointment_scheduling-call-033` | `appointment_scheduling` | 159s | 23 | 92.5 | pass | 3 | none |
| `appointment_scheduling-call-025` | `appointment_scheduling` | 162s | 36 | 91.3 | pass | 2 | none |
| `appointment_scheduling-call-015` | `appointment_scheduling` | 158s | 26 | 88.4 | pass | 2 | none |
| `appointment_scheduling-call-032` | `appointment_scheduling` | 172s | 24 | 88.3 | pass | 2 | none |
| `appointment_scheduling-call-030` | `appointment_scheduling` | 159s | 32 | 86.4 | pass | 2 | none |
| `appointment_scheduling-call-006` | `appointment_scheduling` | 176s | 34 | 86.3 | review | 3 | Patient Bot repeated 3 times: 555-318-4492 |
| `appointment_scheduling-call-017` | `appointment_scheduling` | 150s | 29 | 83.5 | pass | 2 | none |
| `unknown-call-006` | `unknown` | 150s | 31 | 83.4 | pass | 2 | none |
| `medication_refill-call-009` | `medication_refill` | 154s | 26 | 83.1 | pass | 2 | none |

## Hard-Gate Rejections

- `appointment_scheduling-call-022`: duration_below_60s
- `difficult_call_handling-call-002`: duration_below_60s
- `information_gathering-call-006`: duration_unknown; transcript_empty; no_speaker_labeled_turns
- `medication_refill-call-003`: duration_unknown; transcript_empty; no_speaker_labeled_turns
- `medication_refill-call-004`: duration_unknown; transcript_empty; no_speaker_labeled_turns
- `unknown-call-007`: recording_missing
