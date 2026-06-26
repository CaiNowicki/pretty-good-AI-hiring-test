# Pretty Good AI Hiring Test

Python voice-bot test harness for the Pretty Good AI engineering challenge. It
places controlled outbound calls to the assessment number, behaves as a
scenario-driven patient, records realtime events, and writes call artifacts for
review.

## Safety

The app is hard-coded to call only the Pretty Good AI assessment number:

```text
+18054398008
```

Live call targets require `--live` and an interactive confirmation. Single calls
require typing `LIVE`; batches require typing `LIVE ALL`.

## Prerequisites

- Python 3.11 or later
- [ngrok](https://ngrok.com/download) installed and authenticated
- A Twilio account with a verified outbound phone number
- An OpenAI API key with Realtime API access

## One-Time Setup

Open PowerShell at the project root:

```powershell
cd C:\PrettyGoodAI
```

Create a virtual environment and install the project:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Verify the CLI is installed:

```powershell
pgai-call help
```

Copy and fill in the environment file:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Required values:

```text
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1xxxxxxxxxx
PUBLIC_BASE_URL=https://your-ngrok-domain.ngrok-free.dev
OPENAI_API_KEY=sk-...
REALTIME_MODEL=gpt-realtime-2
TRANSCRIPTION_MODEL=gpt-4o-transcribe
```

`PUBLIC_BASE_URL` is the base HTTPS URL only. Do not include a trailing slash or
any path like `/twilio/voice`.

Every new PowerShell window needs the venv activated before `pgai-call` will
work:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

## CLI Shape

The public CLI is intentionally small:

```powershell
# Help
pgai-call help

# Check config, optionally listing scenarios
pgai-call config
pgai-call config --list-scenarios

# Start the webhook server
pgai-call server --port 8000

# Run one specific scenario
pgai-call a01_specific_time --live

# Run one randomized scenario from a group
pgai-call appointment-scheduling --live

# Run every scenario in a group
pgai-call appointment-scheduling --batch --live

# Run every scenario
pgai-call all-scenarios --live
```

Scenario group names:

- `smoke`
- `appointment-scheduling`
- `medication-refill`
- `information-gathering`
- `orthopedic-edge-cases`
- `difficult-call-handling`

Useful aliases are still accepted, such as `appointment`, `medication`,
`refill`, `informational`, `orthopedic`, and `difficult`.

Group calls are randomized by default. Use `--shuffle-seed` for reproducible
scenario and patient-profile selection:

```powershell
pgai-call information-gathering --live --shuffle-seed review-run-1
pgai-call information-gathering --batch --live --shuffle-seed review-run-1
```

For live batches, each next call starts after the previous call writes a
completion event. To add a buffer after each completed call:

```powershell
pgai-call all-scenarios --live --inter-call-delay-seconds 10
```

If a call does not write a completion marker and you want the batch to keep
moving after the wait timeout:

```powershell
pgai-call all-scenarios --live --completion-timeout-seconds 300 --continue-on-completion-timeout
```

Use `--no-wait-for-completion` only when you intentionally want parallel live
calls.

## Live Call Flow

A live call requires three terminals running simultaneously. Open each one from
the project root with the venv activated.

Terminal 1 keeps ngrok running so Twilio can reach your machine. Terminal 2
keeps the local webhook server running and writes artifacts. Terminal 3 starts
the outbound Twilio call.

### Terminal 1: ngrok tunnel

Start the tunnel forwarding your public URL to local port 8000:

```powershell
ngrok http 8000 --domain=your-ngrok-domain.ngrok-free.dev
```

Leave this terminal running for the entire session.

### Terminal 2: webhook server

Start the server:

```powershell
pgai-call server --port 8000 --public-base-url https://your-ngrok-domain.ngrok-free.dev
```

You should see:

```text
INFO: Uvicorn running on http://0.0.0.0:8000
```

Leave this process running. To stop it, press Ctrl+C.

Before placing a call, check the local server:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response: `status: ok` with a timestamp.

Check the public TwiML endpoint in a browser:

```text
https://your-ngrok-domain.ngrok-free.dev/twilio/voice?scenario_id=t01_smoke
```

The response must contain a `<Stream>` element whose URL starts with `wss://`
and ends with `/twilio/media`.

### Terminal 3: place calls

Run one specific scenario:

```powershell
pgai-call a01_specific_time --live --public-base-url https://your-ngrok-domain.ngrok-free.dev
```

Run one randomized scenario from a group:

```powershell
pgai-call medication-refill --live --public-base-url https://your-ngrok-domain.ngrok-free.dev
```

Run a full live batch:

```powershell
pgai-call all-scenarios --live --public-base-url https://your-ngrok-domain.ngrok-free.dev
```

Watch Terminal 2 for incoming connections. A successful call shows:

```text
POST /twilio/voice ... 200 OK
WebSocket /twilio/media [accepted]
connection open
```

Complete artifacts arrive only after the media stream connects and the call
finishes. A folder that only contains `metadata.json`, `events.jsonl`, and
`scenario.yaml` means the call request started but the media stream or recording
callback did not complete.

## Troubleshooting

If PowerShell says `pgai-call` is not recognized, re-activate the venv and rerun
the editable install:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

If server startup fails with `WinError 10048`, another server is already using
port 8000. Find the listener:

```powershell
netstat -ano | findstr :8000
```

Then stop the PID shown on the `LISTENING` line:

```powershell
Stop-Process -Id <PID>
```

If the WebSocket does not connect, check in order:

- Terminal 1 is still running the tunnel
- Terminal 2 is still running the server
- `.env` `PUBLIC_BASE_URL` matches the current ngrok forwarding URL
- The public TwiML response contains `wss://`, not `ws://` or `http://`
- The local health check returns `status: ok`

To test a different tunnel URL without editing `.env`:

```powershell
pgai-call server --port 8000 --public-base-url https://other-tunnel.ngrok-free.app
pgai-call a01_specific_time --live --public-base-url https://other-tunnel.ngrok-free.app
```

## Artifacts

Each call writes artifacts under:

```text
artifacts/calls/<scenario_type>/call-###/
```

Files written per call:

- `metadata.json`: scenario, call plan, Twilio call status
- `events.jsonl`: call boundary, Twilio media, and OpenAI Realtime events
- `scenario.yaml`: copy of the scenario definition used for this run
- `transcript.txt`: speaker-labeled transcript generated from realtime events
- `recording.mp3`: downloaded from Twilio when the recording callback arrives

`analysis.md` is a manual review artifact and is not generated automatically.

The transcript and recording arrive after the call ends via Twilio callbacks,
not immediately when the CLI command exits.

## Patient Personas

Most scenarios use lightweight scenario-local patient facts. Richer personas
live in `src/voicebot/personas/`, including:

- `sofia_reyes_montoya`: calm, organized patient with a hyphenated last name
- `frank_kowalski`: suspicious older patient who escalates around repeated
  identity verification unless the agent explains why
- `patricia_okonkwo`: soft-spoken patient with changing availability
- `george_papadopoulos`: caller focused on insurance and parking details
- `dmitri_volkov`: new patient with an accent and spelling needs
- `carmen_reyes`: refill caller with identity-verification friction
- `aaliyah_washington`: reschedule and referral workflow caller

## Scenario Codes

Smoke:

- `t01_smoke`: new patient appointment, morning preferred

Appointment scheduling:

- `a01_specific_time`: asks for next Tuesday at 10 AM
- `a02_change_of_mind`: starts broad, then changes availability
- `a03_vague_narrow`: vague request that narrows later
- `a04_cancel_no_date`: wants to cancel but does not know the appointment date
- `a05_reschedule_day`: moves an existing Wednesday appointment later in the week
- `a06_closed_hours`: parent asks for Saturday, testing closed-hours handling
- `a07_interruption`: reschedule call with one intentional interruption
- `a07_name_lookup_confusion`: Sofia tests name lookup variations

Medication refill:

- `m01_standard_refill`: established patient refill request
- `m02_refill_no_record`: refill caller with no matching patient record

Information gathering:

- `i01_office_hours`: asks about office hours
- `i02_who_practices`: asks which doctors practice there
- `i03_wait_time`: asks about new-patient wait time
- `i04_insurance`: asks about ambiguous Blue Cross coverage
- `i05_visit_cost`: asks about visit cost

Orthopedic edge cases:

- `e01_medical_emergency`: fall with possible fracture, testing emergency routing
- `e02_symptom_triage`: asks whether knee pain belongs at orthopedics
- `e03_workers_comp`: asks about workers' comp handling
- `e04_minor_caller`: minor tries to book without a parent
- `e05_records_request`: asks to send prior MRI records to another specialist

Difficult call handling:

- `d01_hard_of_hearing`: caller needs repetition and clear speech
- `d02_interrupter`: impatient caller intentionally interrupts
- `d03_background_interruptions`: parent distracted by background noise
- `d04_belligerent_identity`: Frank tests identity-verification de-escalation

## Known Limitations

- The webhook server and ngrok tunnel must both be running before a live call.
- `recording.mp3` and final `transcript.txt` are written by callbacks after the
  call ends, not when the CLI exits.
- Transcripts are generated from OpenAI Realtime transcript events and should be
  reviewed before being used as final bug evidence.
- Patient bot current limitation, no intent to fix: voice gender cues do not
  always match the patient persona.
