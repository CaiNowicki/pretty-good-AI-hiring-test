# Pretty Good AI Hiring Test

Python voice-bot test harness for the Pretty Good AI engineering challenge. It
places controlled outbound calls to the assessment number, behaves as a
scenario-driven patient, records realtime events, and writes call artifacts for
review.

## Safety

The app is hard-coded to call only the Pretty Good AI assessment number:

```
+18054398008
```

Any attempt to dial a different destination fails before reaching Twilio. Live
runs require you to type `LIVE` at a confirmation prompt before any call is
placed.

---

## Prerequisites

Before setup, make sure you have:

- Python 3.11 or later
- [ngrok](https://ngrok.com/download) installed and authenticated
- A Twilio account with a verified outbound phone number
- An OpenAI API key with Realtime API access

---

## One-Time Setup

Open a PowerShell terminal and navigate to the project root:

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

Verify the install worked:

```powershell
pgai-call --help
```

You should see the list of subcommands. If PowerShell says `pgai-call` is not
recognized, the most likely cause is that `pip install` ran outside the
activated venv. Re-activate and re-run `pip install -e ".[dev]"`.

Copy and fill in the environment file:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Required values:

```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+1xxxxxxxxxx
PUBLIC_BASE_URL=https://liftable-nobuko-pseudofeverishly.ngrok-free.dev
OPENAI_API_KEY=sk-...
REALTIME_MODEL=gpt-realtime-2
TRANSCRIPTION_MODEL=gpt-4o-transcribe
```

`PUBLIC_BASE_URL` is your ngrok forwarding URL — the base HTTPS URL only. Do
not include a trailing slash or any path like `/twilio/voice`.

---

## Activating the venv

Every new PowerShell window needs these two lines before `pgai-call` will work:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

`Set-ExecutionPolicy` only affects the current terminal session. You need it
every time you open a new window.

---

## Verify setup without making a call

Before touching the tunnel or server, confirm your `.env` is readable and the
call plan looks right:

```powershell
pgai-call dry-run --scenario t01_smoke
```

This prints the scenario and flags any missing configuration. Nothing is written
to disk and no call is placed.

To see all available scenario codes:

```powershell
pgai-call list-scenarios
```

---

## Dev mode — scaffold artifacts without calling

To prepare a scenario's artifact directory without placing a live call:

```powershell
pgai-call a01_specific_time dev
```

The CLI prints the scenario, confirms this is not a live call, and requires you
to type `DEV` before writing anything. It creates three scaffold files:
`metadata.json`, `events.jsonl`, and `scenario.yaml`.

After the run it asks whether to clean up. Type `DELETE` to remove the scaffold
directory or press Enter to keep it for inspection.

Use dev mode to verify a scenario loads correctly and artifact paths are right
before committing to a live call.

---

## Batch Live Calling

To run all scenarios as a series of live Twilio calls in one command, the
webhook server and tunnel must already be running (see Live Call Flow below).
Then in Terminal 3:

```powershell
pgai-call scenario-call-pipeline --all-scenarios --live
```

The CLI prints the full batch plan and requires you to type `LIVE ALL` before
any calls are placed. Scenarios run in order. For live batches, each next call
starts after the previous call writes a completion event from the webhook server.

To add a small buffer after each completed call before requesting the next one:

```powershell
pgai-call scenario-call-pipeline --all-scenarios --live --inter-call-delay-seconds 10
```

Use `--no-wait-for-completion` only when you intentionally want parallel live
calls.

To run a subset of scenarios as a live batch:

```powershell
pgai-call scenario-call-pipeline --scenario a01_specific_time --scenario m01_standard_refill --live
```

Category shortcuts run one shuffled scenario from a scenario family by default.
Add `--batch` to run every scenario in that category:

```powershell
pgai-call informational --live
pgai-call informational --live --batch
pgai-call medication --live --batch --inter-call-delay-seconds 10
```

---

## Live Call Flow

A live call requires three terminals running simultaneously. Open each one from
the project root with the venv activated.

The terminals have different jobs:

- Terminal 1 keeps ngrok running so Twilio can reach your machine.
- Terminal 2 keeps the local webhook server running and writes artifacts.
- Terminal 3 starts the outbound Twilio call.

Health checks and browser URL checks do not place a call and will not create
complete call artifacts.

### Terminal 1 — ngrok tunnel

Start the tunnel forwarding your public URL to local port 8000:

```powershell
ngrok http 8000 --domain=liftable-nobuko-pseudofeverishly.ngrok-free.dev
```

This binds the tunnel to your permanent ngrok dev domain, so `PUBLIC_BASE_URL`
in `.env` never needs to change. If you use plain `ngrok http 8000` instead,
ngrok assigns a random URL and you will need to update `.env` before each
session.

Leave this terminal running for the entire session.

### Terminal 2 — webhook server

Activate the venv, then start the server:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
pgai-call server --port 8000 --public-base-url https://liftable-nobuko-pseudofeverishly.ngrok-free.dev
```

You should see:
```
INFO: Uvicorn running on http://0.0.0.0:8000
```

Leave this process running. It is not stuck; it is waiting for Twilio webhook
traffic. To stop it, press the keyboard shortcut Ctrl+C. Do not type `Ctrl+C`
as a command.

If startup fails with `WinError 10048`, another server is already using port
8000. Stop the old Terminal 2 process, or find the listener with:

```powershell
netstat -ano | findstr :8000
```

Then stop the PID shown on the `LISTENING` line:

```powershell
Stop-Process -Id <PID>
```

Before placing a call, run two health checks in a separate terminal or browser.

Check the local server:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response: `status: ok` with a timestamp.

Check the public TwiML endpoint in a browser (replace the tunnel URL with yours):

```
https://liftable-nobuko-pseudofeverishly.ngrok-free.dev/twilio/voice?scenario_id=t01_smoke
```

The response must contain a `<Stream>` element whose URL starts with `wss://`
and ends with `/twilio/media`. If it still shows an old tunnel URL, update
`PUBLIC_BASE_URL` in `.env` and restart Terminal 2.

If the browser also requests `/favicon.ico` and the server logs `404 Not Found`,
ignore it. That request comes from the browser tab icon lookup and is not part
of the Twilio call flow.

Leave this terminal running for the entire session.

### Terminal 3 — place a call

Activate the venv, then run a scenario:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
pgai-call a01_specific_time --public-base-url https://liftable-nobuko-pseudofeverishly.ngrok-free.dev
```

The CLI prints the scenario details, warns that it will dial `+18054398008`,
and waits for you to type `LIVE`. After confirmation it creates the Twilio call
and exits. Artifacts are written by the webhook server as the call proceeds.

Watch Terminal 2 for incoming connections. A successful call shows:

```
POST /twilio/voice ... 200 OK
WebSocket /twilio/media [accepted]
connection open
```

Complete artifacts arrive only after the media stream connects and the call
finishes. A folder that only contains `metadata.json`, `events.jsonl`, and
`scenario.yaml` means the call request was started but the media stream or
recording callback did not complete.

### If the WebSocket does not connect

Check in order:

- Terminal 1 is still running the tunnel
- Terminal 2 is still running the server
- `.env` `PUBLIC_BASE_URL` matches the current ngrok forwarding URL
- The public TwiML response contains `wss://` not `ws://` or `http://`
- The local health check returns `status: ok`

To test a different tunnel URL without editing `.env`:

```powershell
pgai-call server --port 8000 --public-base-url https://other-tunnel.ngrok-free.app
pgai-call a01_specific_time --public-base-url https://other-tunnel.ngrok-free.app
```

---

## All CLI Commands

```powershell
# Verify setup — print call plan, no call placed, nothing written
pgai-call dry-run --scenario t01_smoke

# List all runnable scenario codes
pgai-call list-scenarios

# Prepare a scenario without calling (requires typing DEV)
pgai-call a01_specific_time dev

# Place one live call (requires typing LIVE)
pgai-call a01_specific_time

# Run the webhook server
pgai-call server --port 8000

# Prepare artifact scaffolds for all scenarios without calling
pgai-call scenario-call-pipeline --all-scenarios

# Prepare one shuffled artifact scaffold from a scenario category without calling
pgai-call smoke
pgai-call informational
pgai-call appointments
pgai-call medication
pgai-call orthopedic
pgai-call difficult

# Prepare artifact scaffolds for every scenario in one category
pgai-call informational --batch

# Prepare scaffolds for specific scenarios only
pgai-call scenario-call-pipeline --scenario a01_specific_time --scenario m01_standard_refill

# Run all scenarios as a live batch (requires typing LIVE ALL).
# Each next call starts after the previous call completes.
pgai-call scenario-call-pipeline --all-scenarios --live

# Run one shuffled scenario from a category as a live call (requires typing LIVE).
pgai-call informational --live

# Run every scenario in one category as a live batch (requires typing LIVE ALL).
pgai-call informational --live --batch

# Optional: add a 10-second buffer after each completed call
pgai-call scenario-call-pipeline --all-scenarios --live --inter-call-delay-seconds 10

# Run via Python directly if the script is not on PATH
python -m voicebot.cli a01_specific_time dev
python -m voicebot.cli a01_specific_time
```

---

## Artifacts

Each call writes artifacts under:

```
artifacts/calls/<scenario_type>/call-###/
```

Files written per call:

- `metadata.json` — scenario, call plan, Twilio call status
- `events.jsonl` — call boundary, Twilio media, and OpenAI Realtime events
- `scenario.yaml` — copy of the scenario definition used for this run
- `transcript.txt` — speaker-labeled transcript generated from realtime events
- `recording.mp3` — downloaded from Twilio when the recording callback arrives

`analysis.md` is a manual review artifact and is not generated automatically.

The transcript and recording arrive after the call ends via Twilio callbacks, not
immediately when the CLI command exits.

---

## Patient Personas

Most scenarios use lightweight scenario-local patient facts. Two richer personas
live in `src/voicebot/personas/`:

- `sofia_reyes_montoya` — calm, organized patient with a hyphenated last name
  and known lookup variations
- `frank_kowalski` — suspicious older patient who escalates around repeated
  identity verification unless the agent explains why

Common scenario-local profiles:

- `maya_patel` — new or prospective patient, generally cooperative
- `maria_lopez` — scheduling-focused patient with work constraints
- `robert_hayes` — older caller who may be unclear about dates or details
- `taylor_brooks` — parent calling for a child
- `denise_wong` — established patient for refill or records workflows

---

## Scenario Codes

Smoke:

- `t01_smoke` — new patient appointment, morning preferred

Appointment scheduling:

- `a01_specific_time` — asks for next Tuesday at 10 AM
- `a02_change_of_mind` — starts broad, then changes availability
- `a03_vague_narrow` — vague request that narrows later
- `a04_cancel_no_date` — wants to cancel but does not know the appointment date
- `a05_reschedule_day` — moves an existing Wednesday appointment later in the week
- `a06_closed_hours` — parent asks for Saturday, testing closed-hours handling
- `a07_interruption` — reschedule call with one intentional interruption
- `a07_name_lookup_confusion` — Sofia tests name lookup variations

Medication refill:

- `m01_standard_refill` — established patient refill request
- `m02_refill_no_record` — refill caller with no matching patient record

Information gathering:

- `i01_office_hours` — asks about office hours
- `i02_who_practices` — asks which doctors practice there
- `i03_wait_time` — asks about new-patient wait time
- `i04_insurance` — asks about ambiguous Blue Cross coverage
- `i05_visit_cost` — asks about visit cost

Orthopedic edge cases:

- `e01_medical_emergency` — fall with possible fracture, testing emergency routing
- `e02_symptom_triage` — asks whether knee pain belongs at orthopedics
- `e03_workers_comp` — asks about workers' comp handling
- `e04_minor_caller` — minor tries to book without a parent
- `e05_records_request` — asks to send prior MRI records to another specialist

Difficult call handling:

- `d01_hard_of_hearing` — caller needs repetition and clear speech
- `d02_interrupter` — impatient caller intentionally interrupts
- `d03_background_interruptions` — parent distracted by background noise
- `d04_belligerent_identity` — Frank tests identity-verification de-escalation

---

## Known Limitations

- The webhook server and ngrok tunnel must both be running before a live call.
- The `recording.mp3` and final `transcript.txt` are written by Twilio callbacks
  after the call ends, not when the CLI exits.
- Transcripts are generated from OpenAI Realtime transcript events and should be
  reviewed before being used as final bug evidence.
- Patient bot current limitation, no intent to fix: voice gender cues do not
  always match the patient persona.
