# Architecture Design

## Proposed Architecture

The system will be a Python voice-bot runner with four responsibilities: originate calls, manage a real-time patient persona, collect artifacts, and analyze results. Twilio Programmable Voice will place the outbound call to the Pretty Good AI assessment number and stream live call audio to a Python WebSocket service. The service will connect that stream to a speech-to-speech model session, maintain scenario state, and send synthesized patient audio back into the call.

This design favors a real phone call and real-time audio loop over an offline benchmark because the challenge explicitly evaluates voice interaction quality first. Twilio gives us outbound calling, recording, caller-number control, and phone-network realism. A Python service keeps the challenge code readable and lets us own scenario logic, call safety checks, transcripts, and bug-analysis artifacts in one place.

## Components

### CLI Runner

- Loads `.env`.
- Validates the requested scenario id.
- Refuses to dial anything except `+18054398008`.
- Starts one call or a controlled batch.
- Writes call metadata and run status.

### Telephony Adapter

- Creates outbound calls from the single approved caller number.
- Supplies TwiML that connects the live call to the local/public WebSocket endpoint.
- Enables call recording.
- Fetches recording media and call status after completion.

### Realtime Media Server

- Accepts Twilio Media Stream WebSocket connections.
- Converts or forwards phone audio frames as required by the speech model.
- Tracks silence, interruptions, bot speech, and call stop conditions.
- Emits structured `events.jsonl` for later debugging, including explicit per-call start/end markers or flags that transcript generation can use as boundaries.

### Scenario Engine

- Loads scenario definitions from data files.
- Provides patient facts, goals, allowed improvisation, and expected outcome.
- Keeps the bot conversational: it can answer questions, ask clarifying questions, repeat information, and steer back to the goal.
- Supports edge-case behaviors such as mild confusion, interruptions, corrections, and unusual availability.

### Transcript and Artifact Writer

- Stores recordings, transcripts, model events, scenario data, and metadata under one call directory.
- Treats any non-zero-length call as incomplete until both a recording file and speaker-labeled transcript are saved.
- Uses the event-log call-boundary markers instead of guessing call ranges from a shared global log.
- Produces speaker-labeled transcripts with timestamps.
- Marks failed calls separately from final submission calls.

### Analysis Pass

- Reads transcript and scenario expectations.
- Produces candidate bug observations.
- Requires manual review before anything is promoted into `bug-report.md`.

## Data Flow

```text
CLI runner
  -> Twilio outbound call
  -> Pretty Good AI test number
  -> Twilio Media Stream WebSocket
  -> Python realtime media server
  -> speech-to-speech model session
  -> patient audio back to Twilio
  -> call recording + transcript + analysis artifacts
```

## Configuration

Expected environment variables:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `PUBLIC_BASE_URL`
- `OPENAI_API_KEY`
- `REALTIME_MODEL`
- `TRANSCRIPTION_MODEL`

The final `.env.example` should include these names and comments, but no secrets.

## Safety Controls

- Use an explicit constant for the allowed destination: `+18054398008`.
- Validate the `TWILIO_FROM_NUMBER` once and reuse it for all calls.
- Add a `--dry-run` mode that prints the planned call without dialing.
- Add max call duration, max batch size, and per-run confirmation.
- Log every attempted destination number.

## Key Design Tradeoffs

Twilio Media Streams require a public WebSocket endpoint and careful audio handling, but they provide strong control over live turn-taking and artifacts. Direct SIP integrations may reduce some media plumbing, but Twilio remains useful for originating the required outbound call, controlling the caller number, and obtaining recordings.

Automated bug analysis is useful as a first pass, but final reports should be human-reviewed. The graders want useful bugs and clear thinking; a concise, evidence-backed bug report will beat a noisy generated list.
