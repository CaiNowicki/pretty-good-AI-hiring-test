# Bug Report — Pivot Point Orthopedics Voice Agent

Generated from transcript analysis of 10 submitted calls.
All citations reference files in `artifacts/calls/`.

---

## Overall Findings

The most significant finding from this test run is not any individual bug — it is that the agent's behavior during identity verification was sufficiently broken that it was not possible to meaningfully test most of the planned edge case scenarios. Eight of ten calls ended in an escalation after a failed verification loop, before the agent had any opportunity to demonstrate scheduling logic, handle refill requests, manage provider preferences, or respond to edge cases like interruptions, date boundary testing, or ambiguous requests.

This is an important distinction: the limited scenario coverage in these transcripts is not a testing gap — it is itself evidence of a systemic agent failure. The patient bot reached the point of stating a goal in nearly every call. The agent simply never got past verification to act on it.

**A note on patient bot behavior:** The patient bot showed two categories of issues worth disclosing. First, in several calls it reasoned out loud in ways that broke patient persona — "Let me think about the best way to handle that for you" and "Let me think about the best way to get you set up" are internal reasoning patterns, not patient speech. In `appointment_scheduling/call-025`, the patient bot explicitly broke character with "Okay, let me respond as the patient and keep it simple." A few turns were also cut off mid-sentence, likely due to barge-in behavior. Second, several scenario categories did not execute as designed: the hard-of-hearing, impatient caller, and parent/child scenarios all defaulted to standard appointment-scheduling behavior rather than following their specific persona instructions. These calls were filtered out by the selection pipeline and do not appear in the submitted set, but they represent a known patient bot limitation that reduced scenario diversity.

These patient bot issues are noted for transparency but do not explain the agent's failures. The agent's verification loop misbehavior is directly observable from transcript sequencing: it re-requests information the patient just provided, misreads clearly spelled-out names, and escalates mid-exchange while the patient is still actively cooperating. Critically, calls like `smoke/call-002` and `orthopedic_edge_cases/call-006` show clean patient bot behavior throughout and still hit the same verification failure — confirming the agent's record lookup is the failure point, not the patient bot.

---

## BR-001: Agent Greets Every Caller as "James" Regardless of Who Is Calling

**Severity:** High
**Affected Calls:** All 10 submitted calls
**Example:** `orthopedic_edge_cases/call-005/transcript.txt`, turn 2

**What happened:**
Every call begins with the agent asking "Am I speaking with James?" regardless of which patient is calling. Across all 10 calls the actual callers were Maria Lopez, Carmen Reyes, Maya Patel, Marcus Webb, Denise Wong, Dmitri Volkov, and others — none of them James. After callers correct this, the agent in several calls continues addressing them as James anyway: in `orthopedic_edge_cases/call-005`, after the patient never confirmed the name James, the agent responds "I understand, James. For this demo, I can still help you."

**Why it matters:**
This is a first-impression failure on every single call. More seriously, the agent is surfacing what appears to be another patient's name before any identity is established — a potential HIPAA-adjacent data exposure issue. Continuing to use the wrong name after correction signals the agent is not tracking conversation state.

**Expected behavior:**
The agent should greet callers neutrally and establish identity before presenting any patient-specific information. If a caller corrects a name assumption, the agent should immediately adopt the correct name and not revert.

---

## BR-002: All Patients Share the Same Phone Number on File

**Severity:** High
**Affected Calls:** `appointment_scheduling/call-020`, `smoke/call-002`, `orthopedic_edge_cases/call-006`, `unknown/call-003`, `orthopedic_edge_cases/call-004`
**Example:** `smoke/call-002/transcript.txt` and `orthopedic_edge_cases/call-006/transcript.txt`

**What happened:**
The phone number 941-842-0514 appears as the on-file number for every patient across multiple calls, presented without the patient ever providing it. Maya Patel, Denise Wong, Dmitri Volkov, Marcus Webb, and others all apparently have this same number "on file." In several calls the agent reads it back and the patient confirms it — unknowingly validating a number that is not theirs.

**Why it matters:**
This is either a hardcoded demo number being treated as real patient data, or a lookup system returning the same default record regardless of who is calling. Either way the agent is presenting fabricated identity data as confirmed fact. Patients who confirm it are now in the system with incorrect contact information.

**Expected behavior:**
The agent should only present a phone number retrieved from a verified patient record matching the caller's provided identity. It should not volunteer a number the caller has not provided and then ask them to confirm it.

---

## BR-003: Agent Leaks Internal Demo Language to Callers

**Severity:** High
**Affected Calls:** `orthopedic_edge_cases/call-005`, `unknown/call-001`
**Example:** `orthopedic_edge_cases/call-005/transcript.txt`, turn 6

**What happened:**
In two calls, after a date of birth does not match records, the agent responds: "The birthdate doesn't match our records, but for demo purposes, I'll accept it." This phrase appears verbatim in both calls. The agent also says "For this demo, I can still help you" in `orthopedic_edge_cases/call-005`.

**Why it matters:**
A production voice agent should never reveal to a caller that it is running in demo mode, that it is overriding verification logic, or that it is accepting data it knows to be incorrect. A real patient hearing this would question whether their information is being handled properly. It also means the agent is proceeding past a failed verification check on false grounds.

**Expected behavior:**
The agent should either complete verification successfully or clearly explain it cannot proceed and offer appropriate next steps — never reveal internal system state or override verification for convenience.

---

## BR-004: Agent Books Appointment for a Minor Without Consent Check

**Severity:** High
**Affected Call:** `orthopedic_edge_cases/call-005/transcript.txt`, turns 4–20

**What happened:**
The patient provided a date of birth of February 11, 2010, making them 16 years old. The agent bypassed verification with "for demo purposes, I'll accept it" and proceeded to book a full medical appointment — including sending a text confirmation — without any acknowledgment that the patient is a minor, without asking for parental authorization, and without requesting consent documentation.

**Why it matters:**
Scheduling a medical appointment for a minor without parental consent verification is a compliance risk. An orthopedic practice must handle minor patients differently — at minimum by confirming a guardian is authorizing the visit.

**Expected behavior:**
The agent should recognize when a date of birth makes the patient a minor and follow the practice's minor consent policy before proceeding with scheduling.

---

## BR-005: Agent Abandons Identity Verification It Had Enough Information to Complete

**Severity:** High
**Affected Calls:** `appointment_scheduling/call-006`, `appointment_scheduling/call-020`, `appointment_scheduling/call-025`, `unknown/call-002`, `orthopedic_edge_cases/call-004`, `smoke/call-002`, `orthopedic_edge_cases/call-006`, `unknown/call-003`
**Example:** `appointment_scheduling/call-006/transcript.txt`, turns 6–22

**What happened:**
In 8 of 10 calls, the agent collects name, date of birth, and phone number — all three standard verification fields — but still says "I can't proceed further right now" and escalates. The verification loop repeats the same questions 2–3 times per call: name spelling is re-requested after already being confirmed, date of birth is asked for again mid-loop, and the agent presents information back incorrectly before giving up. It is not that the agent lacks the information — it cannot successfully use what it has already collected.

**Note on patient bot contribution:** The patient bot produced some unhelpful turns during these loops — reasoning out loud and one character break in `appointment_scheduling/call-025`. However, the verification failure pattern is consistent across calls where the patient bot behaved cleanly (`smoke/call-002`, `orthopedic_edge_cases/call-006`), confirming this is an agent-side failure.

**Why it matters:**
Identity verification is the prerequisite for every patient task. When it fails despite the patient providing complete, correct, repeated answers, the agent cannot help anyone. This failure prevented meaningful edge case testing in 8 of 10 submitted calls.

**Expected behavior:**
The agent should complete a lookup using name and date of birth as a fallback when phone number matching fails. It should not re-request confirmed information and should not escalate while still in an active, cooperative exchange.

---

## BR-006: Agent Never Attempts to Handle Non-Scheduling Requests

**Severity:** High
**Affected Calls:** `unknown/call-002`, `orthopedic_edge_cases/call-006`
**Examples:**
- `unknown/call-002`: Patient opens with a medication refill request. Agent ignores it, runs identity verification, fails, and escalates without ever acknowledging the refill.
- `orthopedic_edge_cases/call-006`: Patient explicitly states they need records sent to another doctor. Agent ignores the request entirely and follows the same verification-then-escalation path.

**Why it matters:**
Both patients stated their need clearly in their opening turn. The agent acknowledged neither request, made no attempt to address it, and routed both callers to a transfer after a failed verification loop with no context passed about what the patient actually needed.

**Expected behavior:**
The agent should acknowledge the patient's stated need before beginning verification. If verification fails and escalation is necessary, the handoff should include the patient's original request so the receiving team can act on it.

---

## BR-007: Agent Misreads and Misconfirms Patient-Provided Information

**Severity:** Medium
**Affected Calls:** `appointment_scheduling/call-006`, `appointment_scheduling/call-020`, `unknown/call-001`, `unknown/call-003`
**Examples (confirmed against recordings):**
- `appointment_scheduling/call-020`: Patient spells "M-A-R-I-A"; agent reads back "N-A-R-I-A." Same call, agent drops the last two letters of "Lopez" during readback.
- `appointment_scheduling/call-006`: Patient provides 555-318-4492 three times; agent reads back "555-4492" dropping three digits, then asks for "the remaining digits" as if only a partial number was received.
- `unknown/call-001`: Patient gives DOB 2000-06-05; agent reads back "May 6th, 2006" — wrong month and wrong year.
- `unknown/call-003`: Patient spells "D-M-I-T-R-I V-O-L-K-O-V"; agent confirms "Dmitry Zolkov" with DOB "September 27, 1962" when patient said 1963.

**Why it matters:**
The agent mishears what the caller provides, then presents the incorrect version as a confirmation. A patient who says "yes, that's correct" to a garbled readback is now in the system with wrong data. Wrong name, wrong DOB, and wrong phone number together make the patient record unretrievable.

**Expected behavior:**
The agent should accurately reflect what the caller provided. Where uncertainty exists it should ask the caller to re-confirm rather than asserting a garbled version as authoritative.

---

## BR-008: Agent Sends Text Confirmation Before Verifying Contact Number

**Severity:** Medium
**Affected Call:** `orthopedic_edge_cases/call-005/transcript.txt`, turns 27–35

**What happened:**
After booking an appointment, the agent asked if the patient wanted a text confirmation and immediately said "I sent a text confirmation to your phone." The patient then provided their actual number (555-684-2190), at which point the agent revealed it had a different number on file (941-842-0514) — the same placeholder number appearing across all calls. The confirmation was already sent before the discrepancy was discovered.

**Why it matters:**
The confirmation was sent to an unverified number that does not belong to this patient. The patient has no confirmation, and the number that received it may belong to someone else.

**Expected behavior:**
The agent should confirm the patient's contact number before sending any outbound communication. If the number on file differs from what the patient provides, resolve the discrepancy first.

---

## BR-009: Agent Confirms Workers' Comp Cases Without Collecting Required Information

**Severity:** Medium
**Affected Call:** `orthopedic_edge_cases/call-004/transcript.txt`, turns 5–6

**What happened:**
The patient asked whether the practice handles workers' compensation cases. The agent immediately confirmed it does and moved to schedule without asking about the employer, claim number, injury details, or authorization status.

**Why it matters:**
Workers' compensation scheduling requires pre-authorization from the employer's insurer in most states. Confirming an appointment without this information creates an administrative failure when the patient arrives with no claim established.

**Expected behavior:**
The agent should acknowledge that the practice may handle workers' comp, explain that additional information is needed, and either collect it or route to a staff member who can.