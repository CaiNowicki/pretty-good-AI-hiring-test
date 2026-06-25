# Final Call Candidate Review

Generated: 2026-06-25T20:55:02.861+00:00

Selection policy:
- HARD GATE: calls must be at least 60 seconds long, with a non-empty recording and speaker-labeled transcript.
- Ranking favors judgeability: longer calls, more turns, speaker balance, and transcript coherence.
- Ranking does not reward success, failure, or whether either bot looks good.
- Automated first pass flags policy, factual, flow, and voice-quality issues for reviewer triage.
- Manual listening/review is still required before a call is included in the final package.

Discovered calls: 63
Eligible after hard gates and severe sensibility checks: 51
Rejected by hard gate: 12

## Automated First Pass

Policy: 2 | Factual: 48 | Flow: 72 | Voice quality: 20

## Top 10 Review Queue

| Rank | Call | Type | Duration | Turns | Score | Review | Issues | Flags |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| 1 | `orthopedic_edge_cases-call-005` | `orthopedic_edge_cases` | 240s | 38 | 93.3 | pass | 1 | none |
| 2 | `appointment_scheduling-call-020` | `appointment_scheduling` | 199s | 33 | 86.3 | pass | 3 | none |
| 3 | `appointment_scheduling-call-006` | `appointment_scheduling` | 176s | 34 | 84.8 | pass | 3 | none |
| 4 | `appointment_scheduling-call-025` | `appointment_scheduling` | 162s | 36 | 84.5 | pass | 3 | none |
| 5 | `unknown-call-002` | `unknown` | 162s | 31 | 80.2 | pass | 3 | none |
| 6 | `orthopedic_edge_cases-call-004` | `orthopedic_edge_cases` | 145s | 33 | 79.1 | pass | 3 | none |
| 7 | `unknown-call-001` | `unknown` | 166s | 32 | 78.8 | pass | 0 | none |
| 8 | `smoke-call-002` | `smoke` | 158s | 31 | 77.0 | pass | 3 | none |
| 9 | `orthopedic_edge_cases-call-006` | `orthopedic_edge_cases` | 160s | 26 | 74.7 | pass | 2 | none |
| 10 | `unknown-call-003` | `unknown` | 162s | 35 | 72.6 | review | 3 | long_same_speaker_run_5 |

## Manual Review Checklist

- Listen to the recording and confirm the transcript matches both speakers.
- Check every automated issue flag against the recording before promoting it.
- Confirm the dialogue stays sensible through the end, not just near the bug evidence.
- Exclude calls where patient-bot glitches create the apparent issue.
- Exclude calls where the agent-bot outcome is unjudgeable because the call setup degraded.
- Prefer calls that expose decision points, recovery behavior, clarifications, or safety handling.

## Selected Calls With Review Flags

| Rank | Call | Type | Duration | Turns | Score | Review | Issues | Flags |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| 10 | `unknown-call-003` | `unknown` | 162s | 35 | 72.6 | review | 3 | long_same_speaker_run_5 |

## Automated Issues In Selected Calls

| Call | Category | Severity | Source | Finding | Evidence |
| --- | --- | --- | --- | --- | --- |
| `orthopedic_edge_cases-call-005` | policy | medium | agent_bot | Minor or guardian context may not have been acknowledged by the agent. | PGAI Agent: This call may be recorded for quality and training purposes. Para español, oprima el dos. |
| `appointment_scheduling-call-020` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...tty Good AI. Am I speaking with James? Patient Bot: This is Maria Lopez. You may have the wrong patient if you were expecting James. I’ll wait for your next question. PGAI Agent: Thanks for cla... |
| `appointment_scheduling-call-020` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...you to a representative. Please wait PGAI Agent: Hello, you've reached the Pretty Good AI test line. Goodbye. Patient Bot: Okay, thank you. Goodbye. |
| `appointment_scheduling-call-020` | flow | low | agent_bot | Agent utterance may be clipped or missing context. | ..., 1980, is that correct? Would you like to use your phone number to look up your records? you have on file with us. If you're not sure, just let me know and we'll confirm your name and date of birth again... |
| `appointment_scheduling-call-006` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...PGAI Agent: Am I speaking with James? Patient Bot: This is Maria Lopez. You may have the wrong patient. I’ll wait for you to confirm who you’re trying to reach. PGAI Agent: Please provide the... |
| `appointment_scheduling-call-006` | factual | high | agent_bot | Agent may have confirmed an incorrect phone number or stale record. | ...de the remaining digits so I can complete the lookup? PGAI Agent: 그렇구나. Patient Bot: That phone number is not mine. My phone number is 555-318-4492. PGAI Agent: I have your number as 555-318-4492. Is that... |
| `appointment_scheduling-call-006` | flow | low | agent_bot | Agent utterance may be clipped or missing context. | ...ll your last name, Lopez? Would you like me to look up your record using the phone number you have on file with us? If so, please provide that number. If you're not sure, I can confirm your name? Could yo... |
| `appointment_scheduling-call-025` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...AI Agent: Am I speaking with James? Patient Bot: This is Maria Lopez, so you may have the wrong patient. Hi, I'd like to make an appointment for next Tuesday at 10 AM. PGAI Agent: Thanks for cl... |
| `appointment_scheduling-call-025` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...esentative. PGAI Agent: Please wait. PGAI Agent: Hello, you've reached the Pretty Good AI test line. Goodbye. Patient Bot: Goodbye. |
| `appointment_scheduling-call-025` | flow | low | agent_bot | Agent utterance may be clipped or missing context. | ...ou like to use your phone number to look up your record? If so, please provide the number you have on file with us. If you're not sure, I can confirm your name and date of birth again. Which would you pre... |
| `unknown-call-002` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...ty Good AI. Am I speaking with James? Patient Bot: This is Carmen Reyes. You may have the wrong patient if you’re expecting James. Hi, I need to get a refill on my blood pressure medication. Th... |
| `unknown-call-002` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...d a refill on my blood pressure medication. PGAI Agent: You've reached the Pretty Good AI Test Line. Goodbye. Patient Bot: Okay, goodbye. |
| `unknown-call-002` | flow | low | agent_bot | Agent utterance may be clipped or missing context. | ...Carmen, letter by letter? Would you like me to look up your record using the phone number you have on file with us? If so, please provide that number. If you're not sure, I can confirm your name and date... |
| `orthopedic_edge_cases-call-004` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...etty Good AI. PGAI Agent: Am I speaking with James? Patient Bot: I think you may have the wrong patient—this is Marcus Webb. Hi, I hurt my ankle at work a couple days ago and I need to come in.... |
| `orthopedic_edge_cases-call-004` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...please wait. Patient Bot: Okay, I’ll PGAI Agent: Hello, you've reached the Pretty Good AI test line. Goodbye. Patient Bot: Goodbye. |
| `orthopedic_edge_cases-call-004` | flow | low | agent_bot | Agent utterance may be clipped or missing context. | ...ou like to use your phone number to look up your record? If so, please provide the number you have on file with us. If you're not sure, I can confirm your name. I have your phone number as 555 814-3309, a... |
| `smoke-call-002` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...etty Good AI. Am I speaking with James? Patient Bot: This is Maya Patel. You may have the wrong patient if you were expecting James. Hi, I'm hoping to make an appointment. I'm a new patient. PG... |
| `smoke-call-002` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...pport team. PGAI Agent: Please wait. PGAI Agent: Hello, you've reached the Pretty Good AI test line. Goodbye. Patient Bot: Goodbye. |
| `smoke-call-002` | flow | low | agent_bot | Agent utterance may be clipped or missing context. | ...ou like to use your phone number to look up your record? If so, please provide the number you have on file with us. If you're not sure, I can confirm your name and date of birth again. Let me know what yo... |
| `orthopedic_edge_cases-call-006` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ..., part of Pretty Good AI. Am I speaking with James? Patient Bot: I think you may have the wrong patient. The caller is Denise Wong. Hi, I don't need an appointment. I actually need to get some... |
| `orthopedic_edge_cases-call-006` | flow | medium | agent_bot | Transfer path appears to end at the test line instead of a meaningful resolution. | ...a represent PGAI Agent: Please wait. PGAI Agent: Hello, you've reached the Pretty Good AI test line. Goodbye. Patient Bot: Okay, thanks for your time. |
| `unknown-call-003` | factual | high | agent_bot | Agent may have assumed or surfaced the wrong patient identity. | ...make an appointment. I am a new patient. I have a problem with my knee. You may have the wrong patient name though—the caller is Dmitri Volkov. PGAI Agent: Can you please provide your date of... |
| `unknown-call-003` | flow | medium | conversation | Long same-speaker run may indicate interruption, grouping, or stalled dialogue. | Longest same-speaker run: 5 |
| `unknown-call-003` | flow | low | agent_bot | Agent utterance may be clipped or missing context. | ...ou like to use your phone number to look up your record? If so, please provide the number you have on file with us. If you're not sure, I can confirm your name and date of birth again. Which would you pre... |

## Near Misses

| Call | Type | Duration | Turns | Score | Review | Issues | Flags |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| `appointment_scheduling-call-031` | `appointment_scheduling` | 185s | 34 | 83.9 | pass | 3 | none |
| `appointment_scheduling-call-023` | `appointment_scheduling` | 170s | 33 | 82.3 | pass | 2 | none |
| `appointment_scheduling-call-030` | `appointment_scheduling` | 159s | 32 | 77.4 | pass | 3 | none |
| `appointment_scheduling-call-018` | `appointment_scheduling` | 163s | 36 | 75.0 | review | 2 | repeated_utterance_count_5 |
| `appointment_scheduling-call-017` | `appointment_scheduling` | 150s | 29 | 74.0 | pass | 2 | none |
| `appointment_scheduling-call-015` | `appointment_scheduling` | 158s | 26 | 73.4 | pass | 2 | none |
| `appointment_scheduling-call-024` | `appointment_scheduling` | 133s | 32 | 73.4 | pass | 2 | none |
| `appointment_scheduling-call-032` | `appointment_scheduling` | 172s | 24 | 73.3 | pass | 2 | none |
| `orthopedic_edge_cases-call-001` | `orthopedic_edge_cases` | 156s | 35 | 72.3 | review | 2 | repeated_utterance_count_4 |
| `appointment_scheduling-call-016` | `appointment_scheduling` | 144s | 28 | 71.9 | pass | 2 | none |

## Hard-Gate Rejections

- `appointment_scheduling-call-022`: duration_below_60s
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
