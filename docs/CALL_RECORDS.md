# Call Records

Final package location: final_submission/call_records/

Calls are organized by type first. Inside each type directory, 00_selected_top_10 contains any priority review calls for that type, and 01_all_over_60_seconds contains every local recording of that type verified as longer than 60 seconds.

Counts:

- Selected top recordings: 10
- Grouped recordings over 60 seconds: 51
- Legacy recordings over 60 seconds: 13
- Total over-60 recordings in the complete set: 64

Metadata copied into final_submission is sanitized for the Twilio account SID, outbound phone number, and ngrok base URL. Recordings, transcripts, scenarios, and event logs are otherwise preserved.

## Type Summary

| Type | Selected top 10 count | All over-60 count |
| --- | ---: | ---: |
| appointment_scheduling | 3 | 23 |
| difficult_call_handling | 0 | 3 |
| information_gathering | 0 | 10 |
| legacy | 0 | 13 |
| medication_refill | 0 | 2 |
| orthopedic_edge_cases | 3 | 6 |
| smoke | 1 | 2 |
| unknown | 3 | 5 |

## Top 10 Priority Recordings

| Rank | Call | Type | Duration seconds | Score | Review |
| --- | --- | --- | ---: | ---: | --- |
| 1 | orthopedic_edge_cases-call-005 | orthopedic_edge_cases | 240 | 93.3 | pass |
| 2 | appointment_scheduling-call-020 | appointment_scheduling | 198.8 | 86.3 | pass |
| 3 | appointment_scheduling-call-006 | appointment_scheduling | 176.1 | 84.8 | pass |
| 4 | appointment_scheduling-call-025 | appointment_scheduling | 162.4 | 84.5 | pass |
| 5 | unknown-call-002 | unknown | 161.5 | 80.2 | pass |
| 6 | orthopedic_edge_cases-call-004 | orthopedic_edge_cases | 145.1 | 79.1 | pass |
| 7 | unknown-call-001 | unknown | 166.4 | 78.8 | pass |
| 8 | smoke-call-002 | smoke | 157.9 | 77 | pass |
| 9 | orthopedic_edge_cases-call-006 | orthopedic_edge_cases | 159.5 | 74.7 | pass |
| 10 | unknown-call-003 | unknown | 162.2 | 72.6 | review |

## Complete Over-60-Second Recording Set

| Call | Type | Duration seconds | Priority | Duration source |
| --- | --- | ---: | --- | --- |
| appointment_scheduling-call-001 | appointment_scheduling | 129.8 |  | grouped |
| appointment_scheduling-call-006 | appointment_scheduling | 176.1 | Top 3 | grouped |
| appointment_scheduling-call-015 | appointment_scheduling | 157.8 |  | grouped |
| appointment_scheduling-call-016 | appointment_scheduling | 144.4 |  | grouped |
| appointment_scheduling-call-017 | appointment_scheduling | 150.1 |  | grouped |
| appointment_scheduling-call-018 | appointment_scheduling | 162.9 |  | grouped |
| appointment_scheduling-call-019 | appointment_scheduling | 60 |  | grouped |
| appointment_scheduling-call-020 | appointment_scheduling | 198.8 | Top 2 | grouped |
| appointment_scheduling-call-021 | appointment_scheduling | 91.2 |  | grouped |
| appointment_scheduling-call-023 | appointment_scheduling | 170 |  | grouped |
| appointment_scheduling-call-024 | appointment_scheduling | 133.5 |  | grouped |
| appointment_scheduling-call-025 | appointment_scheduling | 162.4 | Top 4 | grouped |
| appointment_scheduling-call-026 | appointment_scheduling | 129.4 |  | grouped |
| appointment_scheduling-call-027 | appointment_scheduling | 136.5 |  | grouped |
| appointment_scheduling-call-028 | appointment_scheduling | 98.9 |  | grouped |
| appointment_scheduling-call-029 | appointment_scheduling | 151.2 |  | grouped |
| appointment_scheduling-call-030 | appointment_scheduling | 159 |  | grouped |
| appointment_scheduling-call-031 | appointment_scheduling | 184.8 |  | grouped |
| appointment_scheduling-call-032 | appointment_scheduling | 172.3 |  | grouped |
| appointment_scheduling-call-033 | appointment_scheduling | 159.2 |  | grouped |
| appointment_scheduling-call-034 | appointment_scheduling | 100.4 |  | grouped |
| appointment_scheduling-call-035 | appointment_scheduling | 107.5 |  | grouped |
| appointment_scheduling-call-036 | appointment_scheduling | 98.2 |  | grouped |
| difficult_call_handling-call-001 | difficult_call_handling | 128 |  | grouped |
| difficult_call_handling-call-003 | difficult_call_handling | 135.3 |  | grouped |
| difficult_call_handling-call-004 | difficult_call_handling | 142.8 |  | grouped |
| information_gathering-call-007 | information_gathering | 115.5 |  | grouped |
| information_gathering-call-008 | information_gathering | 154 |  | grouped |
| information_gathering-call-009 | information_gathering | 149.3 |  | grouped |
| information_gathering-call-010 | information_gathering | 99.4 |  | grouped |
| information_gathering-call-011 | information_gathering | 91.8 |  | grouped |
| information_gathering-call-012 | information_gathering | 78.6 |  | grouped |
| information_gathering-call-013 | information_gathering | 115.8 |  | grouped |
| information_gathering-call-014 | information_gathering | 131.1 |  | grouped |
| information_gathering-call-015 | information_gathering | 156 |  | grouped |
| information_gathering-call-016 | information_gathering | 97.6 |  | grouped |
| medication_refill-call-005 | medication_refill | 135.9 |  | grouped |
| medication_refill-call-006 | medication_refill | 127.9 |  | grouped |
| orthopedic_edge_cases-call-001 | orthopedic_edge_cases | 156.2 |  | grouped |
| orthopedic_edge_cases-call-002 | orthopedic_edge_cases | 109.4 |  | grouped |
| orthopedic_edge_cases-call-003 | orthopedic_edge_cases | 166.3 |  | grouped |
| orthopedic_edge_cases-call-004 | orthopedic_edge_cases | 145.1 | Top 6 | grouped |
| orthopedic_edge_cases-call-005 | orthopedic_edge_cases | 240 | Top 1 | grouped |
| orthopedic_edge_cases-call-006 | orthopedic_edge_cases | 159.5 | Top 9 | grouped |
| smoke-call-001 | smoke | 150.3 |  | grouped |
| smoke-call-002 | smoke | 157.9 | Top 8 | grouped |
| unknown-call-001 | unknown | 166.4 | Top 7 | grouped |
| unknown-call-002 | unknown | 161.5 | Top 5 | grouped |
| unknown-call-003 | unknown | 162.2 | Top 10 | grouped |
| unknown-call-004 | unknown | 139.4 |  | grouped |
| unknown-call-005 | unknown | 110.4 |  | grouped |
| legacy-call-001 | legacy | 176.6 |  | mp3 frame scan |
| legacy-call-002 | legacy | 146.9 |  | mp3 frame scan |
| legacy-call-003 | legacy | 265.5 |  | mp3 frame scan |
| legacy-call-004 | legacy | 151.4 |  | mp3 frame scan |
| legacy-call-005 | legacy | 235.1 |  | mp3 frame scan |
| legacy-call-006 | legacy | 73.7 |  | mp3 frame scan |
| legacy-call-007 | legacy | 72.9 |  | mp3 frame scan |
| legacy-call-008 | legacy | 181.8 |  | mp3 frame scan |
| legacy-call-009 | legacy | 124.5 |  | mp3 frame scan |
| legacy-call-010 | legacy | 186.8 |  | mp3 frame scan |
| legacy-call-012 | legacy | 139.3 |  | mp3 frame scan |
| legacy-call-013 | legacy | 157.8 |  | mp3 frame scan |
| legacy-call-014 | legacy | 131.7 |  | mp3 frame scan |
