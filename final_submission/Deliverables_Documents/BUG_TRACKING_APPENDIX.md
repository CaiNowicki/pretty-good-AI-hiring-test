# Bug Tracking Appendix - Pivot Point Orthopedics Voice Agent

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
| AGT-010 | Text sent before phone verification | High | 1 | 1 |
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

