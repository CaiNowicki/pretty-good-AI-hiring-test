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

Any attempt to dial a different destination fails before reaching Twilio. Live
runs also require a typed confirmation before the call is placed.

## Setup

```powershell
python -m venv ./venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Fill in `.env` if it was newly created:

```text
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
PUBLIC_BASE_URL=https://your-public-tunnel.ngrok-free.app
OPENAI_API_KEY=...
REALTIME_MODEL=gpt-realtime-2
TRANSCRIPTION_MODEL=gpt-4o-transcribe
```

For live calls, the app needs a public HTTPS base URL that can reach the local
webhook server. Put your ngrok forwarding URL in `PUBLIC_BASE_URL` once, using
the base URL only. Do not include `/twilio/voice` or `/twilio/media`.

If PowerShell blocks activation, the `Set-ExecutionPolicy` command above enables
scripts for the current terminal session only.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Activation is per terminal. If you open a new PowerShell window, run those two
lines there too.

## Dev Demo

Prepare a scenario without placing a live call:

```powershell
pgai-call a01_specific_time dev
```

The command prints the selected scenario, confirms this is not a live call, and
requires `DEV` before it writes anything. It creates scaffold files only:
`metadata.json`, `events.jsonl`, and `scenario.yaml`.

After the dev run, the CLI asks whether to delete the generated scaffold
directory. Type `DELETE` to clean up the dev artifact files, or press Enter to
keep them for inspection.

## Live Call Flow

Before the first live call, make sure `.env` contains your ngrok forwarding URL:

```text
PUBLIC_BASE_URL=https://your-public-tunnel.ngrok-free.app
```

Use the base URL only. Do not include `/twilio/voice` or `/twilio/media`.

Use three terminals for a live call.

Terminal 1: make sure ngrok is forwarding your public URL to local port `8000`.
If the tunnel is already running in your ngrok account, leave it running. If you
need to start it locally, use your normal ngrok command. A basic tunnel looks
like this:

```powershell
ngrok http 8000
```

Terminal 2: start the local webhook server and leave it running. If this is a
new PowerShell window, activate the venv first:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Then start the server:

```powershell
pgai-call server --port 8000
```

The app derives the WebSocket URL automatically. Twilio calls
`/twilio/voice`, and the TwiML returned by this app points Media Streams to:

```text
wss://your-public-tunnel.ngrok-free.app/twilio/media
```

Before placing a live call, verify the local server is healthy:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Then check the public TwiML URL in a browser:

```text
https://your-public-tunnel.ngrok-free.app/twilio/voice?scenario_id=t01_smoke
```

The response should contain a `<Stream>` URL beginning with `wss://` and ending
in `/twilio/media`. If it points at an old tunnel, update `PUBLIC_BASE_URL` in
`.env`, then restart the server.

Terminal 3: place one live scenario call. This is a new PowerShell window, so
activate the venv here too:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Then run:

```powershell
pgai-call a01_specific_time
```

The command prints the scenario, warns that it will call `+18054398008`, and
requires `LIVE` before it creates the Twilio call.

If the WebSocket does not connect, check these first:

- Terminal 1 is still running the tunnel.
- Terminal 2 is still running the server.
- `.env` has the current `https://...` forwarding URL in `PUBLIC_BASE_URL`.
- The public base URL is HTTPS, not HTTP, WS, or WSS.
- The public `/twilio/voice` response contains `wss://.../twilio/media`.

If you temporarily need to test a different tunnel without editing `.env`, both
the server and scenario commands accept `--public-base-url`:

```powershell
pgai-call server --port 8000 --public-base-url https://temporary-tunnel.ngrok-free.app
pgai-call a01_specific_time --public-base-url https://temporary-tunnel.ngrok-free.app
```

## Supporting Commands

List runnable scenario codes:

```powershell
pgai-call list-scenarios
```

Prepare all scenario artifact scaffolds without placing calls:

```powershell
pgai-call scenario-call-pipeline --all-scenarios
```

Run all scenarios through Twilio as a live series of call requests:

```powershell
pgai-call scenario-call-pipeline --all-scenarios --live
```

The command requires `LIVE ALL` before it starts the batch. Add
`--inter-call-delay-seconds 180` if you want a pause between scenario call
requests.

Run the CLI through Python instead of the installed script:

```powershell
python -m voicebot.cli a01_specific_time dev
```

## Artifacts

New call artifacts are grouped under:

```text
artifacts/calls/<scenario_type>/call-###/
```

Each run prepares:

- `metadata.json`: scenario, call plan, limits, Twilio call status.
- `events.jsonl`: call boundary events, Twilio media events, realtime events.
- `scenario.yaml`: copied scenario definition used for the run.
- `transcript.txt`: speaker-labeled transcript generated from realtime events.
- `recording.mp3`: downloaded from Twilio when the recording callback arrives.

`analysis.md` is still a manual review artifact.

## Patient Personas

Most scenarios use lightweight scenario-local patient facts. Two richer personas
live in `src/voicebot/personas/`:

- `sofia_reyes_montoya`: calm, organized patient with a hyphenated last name and
  known lookup variations.
- `frank_kowalski`: suspicious older patient who escalates around repeated
  identity verification unless the agent explains why the information is needed.

Common scenario profiles include:

- `maya_patel`: new or prospective patient, generally cooperative.
- `maria_lopez`: scheduling-focused patient with work or availability constraints.
- `robert_hayes`: older caller who may be unclear about dates, cost, or details.
- `taylor_brooks`: parent calling for a child.
- `denise_wong`: established patient for refill or records workflows.

## Scenario Codes

Smoke:

- `t01_smoke`: new patient appointment, morning preferred.

Appointment scheduling:

- `a01_specific_time`: asks for next Tuesday at 10 AM.
- `a02_change_of_mind`: starts broad, then changes availability.
- `a03_vague_narrow`: vague appointment request that narrows later.
- `a04_cancel_no_date`: wants to cancel but does not know the appointment date.
- `a05_reschedule_day`: moves an existing Wednesday appointment later in the week.
- `a06_closed_hours`: parent asks for Saturday, testing closed-hours handling.
- `a07_interruption`: reschedule call with one intentional interruption.
- `a07_name_lookup_confusion`: Sofia tests name lookup variations.

Medication refill:

- `m01_standard_refill`: established patient refill request.
- `m02_refill_no_record`: refill caller with no matching patient record.

Information gathering:

- `i01_office_hours`: asks about office hours.
- `i02_who_practices`: asks which doctors practice there.
- `i03_wait_time`: asks about new-patient wait time.
- `i04_insurance`: asks about ambiguous Blue Cross coverage.
- `i05_visit_cost`: asks about visit cost.

Orthopedic edge cases:

- `e01_medical_emergency`: fall with possible fracture, testing emergency routing.
- `e02_symptom_triage`: asks whether knee pain belongs at orthopedics.
- `e03_workers_comp`: asks about workers' comp handling.
- `e04_minor_caller`: minor tries to book without a parent.
- `e05_records_request`: asks to send prior MRI records to another specialist.

Difficult call handling:

- `d01_hard_of_hearing`: caller needs repetition and clear speech.
- `d02_interrupter`: impatient caller intentionally interrupts.
- `d03_background_interruptions`: parent is distracted by background interruptions.
- `d04_belligerent_identity`: Frank tests identity-verification de-escalation.

## Known Limitations

The webhook server and public tunnel must be running before live calls. Recording
download depends on Twilio successfully posting the recording callback. The
generated transcript comes from realtime transcript events and should be reviewed
before being used as final evidence.
