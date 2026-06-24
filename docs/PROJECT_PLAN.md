# Pretty Good AI Challenge Project Plan

## Objective

Build a Python voice-bot test harness that calls only `+18054398008`, behaves like a realistic patient, records and transcribes at least 10 full conversations, and produces a useful bug report with supporting evidence.

The submission should optimize for the evaluation order in the prompt:

1. Lucid, natural voice conversations.
2. Useful bugs and quality observations.
3. Working code that makes real calls.
4. Clear reasoning in docs and Loom.
5. Evidence of iteration.
6. Clean, readable code.

## Non-Negotiable Constraints

- The dial target must be hardcoded or allowlisted to `+18054398008`.
- Use exactly one outbound caller number for all submitted calls.
- Do not call the number shown on the Athena confirmation screen.
- Do not commit API keys, telephony credentials, call recordings with secrets, or `.env`.
- Submit minimum 10 good calls, each usually 1-3 minutes, with both recording and transcript.
- Recordings must be `ogg` or `mp3`.

## Recommended Technical Direction

Use Twilio Programmable Voice to originate the outbound call and bridge media to a Python WebSocket service with bidirectional Media Streams. The Python service manages the patient persona, scenario state, speech-to-speech model session, event logs, and artifact writing. Twilio should also record the call so we have a complete audio artifact even if transcript labeling needs cleanup afterward.

The first implementation milestone should prove one coherent live call end-to-end before adding scenario breadth. The challenge is judged on call quality before code, so low latency, sensible turn-taking, interruption handling, and clear audio matter more than a fancy evaluator.

## Phases

### Phase 0: Product Familiarization - Complete

- [x] Create a test account at `pgai.us/athena`.
- [x] Walk through the patient-facing flow and note likely office details exposed by the product.
- [x] Save lightweight notes about appointment types, insurance phrasing, office-hours expectations, and normal patient vocabulary.
- [x] Do not call the confirmation-screen number.
- [x] Maintain observations in `docs/PRODUCT_OBSERVATIONS.md` so scenario design reflects real product behavior without treating manual notes as final bug evidence.

### Phase 1: Baseline Voice Loop - In Progress

- [x] Set up telephony credentials, public tunnel URL, and one verified outbound caller number.
- [x] Build the smallest Python flow that prepares one call to the allowlisted test number.
- [x] Connect live audio between the phone call and the bot runtime.
- [ ] Confirm the bot can greet, listen, answer, and hang up naturally. Smoke call proved conversation, but prompt and automatic stopping need polish before final calls.
- [x] Save one test recording and transcript as an internal calibration artifact.

Exit criteria:

- The call lasts at least 60 seconds.
- Both sides are intelligible.
- Bot does not talk over the agent except when intentionally testing barge-in.
- The bot can pursue a simple scheduling goal without freezing.

### Phase 2: Scenario Engine

- Represent each scenario as data: goal, patient profile, required facts, optional edge behavior, success criteria, and stop conditions.
- Add guardrails so the bot never reveals it is a test harness unless the scenario calls for meta behavior.
- Give the bot an active but realistic strategy: answer direct questions, ask follow-ups, correct misunderstandings, and steer back to the goal.
- Add deterministic limits: max call duration, max silence, max turns, and emergency stop.

Exit criteria:

- At least 12 scenarios are runnable locally.
- Bot responses vary naturally while preserving the scenario goal.
- Failed or short calls are marked as retries, not submitted as final evidence.

### Phase 3: Artifact Pipeline

- For each call, create a unique call directory.
- Store metadata, raw event log, recording, transcript, bot scenario, and post-call analysis.
- Normalize transcripts into speaker-labeled text: `Patient Bot` and `PGAI Agent`.
- Keep enough timestamps to cite exact bug locations.
- Convert/download recordings to `mp3` or `ogg`.

Suggested layout:

```text
artifacts/
  calls/
    call-001/
      metadata.json
      scenario.yaml
      transcript.txt
      analysis.md
      recording.mp3
      events.jsonl
  bug-report.md
```

### Phase 4: Bug Analysis

- Run an automated first pass that identifies policy, factual, flow, and voice-quality issues.
- Manually review every submitted call before writing final bug reports.
- Prefer fewer stronger bugs over many weak observations.
- Cite each bug with call id, timestamp, transcript excerpt, expected behavior, actual behavior, and severity.

Severity guide:

- `High`: patient-impacting scheduling, medication, insurance, safety, or major task-completion failure.
- `Medium`: confusing, inconsistent, or brittle behavior that could degrade real patient experience.
- `Low`: minor quality issue that is worth noting but not central.

### Phase 5: Submission Polish

- README: single-command run after setup, environment variables, call safety warning.
- Architecture doc: 1-2 paragraphs plus a simple component list.
- Bug report: concise, evidence-backed, linked to transcript and recording.
- Loom walkthrough: under 5 minutes, focused on choices, tradeoffs, demo, and results.
- AI debugging screen recording: show one real defect, prompts used, diagnosis, code change, and verification.

## Schedule

Assuming 6-12 hours:

- 45 minutes: product familiarization and repo setup.
- 2-3 hours: first end-to-end call.
- 1-2 hours: scenario engine and artifact organization.
- 1-2 hours: run and review 10-15 calls.
- 1 hour: bug report and cleanup.
- 45 minutes: README, architecture doc, Loom outline.

## Risks

- Voice latency or awkward turn-taking causes rejection before code review.
- The bot completes calls but does not steer toward testable outcomes.
- Recordings or transcripts are missing one side of the conversation.
- Scenario prompts are too scripted and sound like a benchmark.
- The implementation accidentally permits dialing a non-test number.
- We over-focus on the basic scheduling happy path even though manual exploration already showed it can work.

## Success Checklist

- [ ] One outbound caller number selected and documented in E.164 format.
- [ ] Dial target allowlist enforced.
- [ ] 10 final calls are 1-3 minutes and coherent.
- [ ] Each final call has `mp3` or `ogg` recording.
- [ ] Each final call has speaker-labeled transcript.
- [ ] Bug report cites exact calls and timestamps.
- [ ] README includes setup, run, env vars, and cost warning.
- [ ] `.env.example` exists.
- [ ] Loom links are ready.
