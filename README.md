# Pretty Good AI Hiring Test

Python voice-bot test harness for the Pretty Good AI engineering challenge.

Current status: Phase 1 baseline scaffold is in progress. The code can produce
a safe dry-run call plan and exposes Twilio webhook endpoints, but it should not
be used for final calls until credentials, a public URL, and the realtime audio
bridge are configured and tested.

## Safety

The app is designed to call only the Pretty Good AI assessment number:

```text
+18054398008
```

Any attempt to dial a different destination should fail before reaching Twilio.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Then fill in `.env` with Twilio, public tunnel, and OpenAI credentials.

## Dry Run

Dry-run mode prints the call plan without placing a call:

```powershell
python -m voicebot.cli dry-run
```

## Webhook Server

Run the local Twilio webhook server:

```powershell
python -m voicebot.cli server --port 8000
```

Expose it with a public HTTPS tunnel and set `PUBLIC_BASE_URL` to that public
URL. Twilio will call `/twilio/voice`, which returns TwiML connecting the call
to `/twilio/media`.

## Place One Call

Only run this after `.env` is configured and the webhook server is reachable
from Twilio:

```powershell
python -m voicebot.cli call --scenario t01_smoke
```

Artifacts are written under `artifacts/calls/`.
