The patient bot uses the OpenAI Realtime API over a bidirectional WebSocket,
with Twilio handling the outbound call, caller-number control, and recording.
Scenario definitions and patient personas live in YAML files rather than code
— this keeps the runtime logic stable while making it easy to add, revise, or
retune scenarios without touching the bridge. Early calibration calls sounded
scripted; moving facts and behavioral constraints into data rather than code
was what made the conversations feel natural.

The initial implementation concentrated too much in a single class.
RealtimeBridge grew to nearly two thousand lines covering audio forwarding,
turn-taking, response construction, transcript classification, and completion
evaluation. A proactive refactor split these into focused modules —
patient_response_builders, conversation_classifier, openai_builders —
with RealtimeBridge reduced to an async orchestrator that calls into them.
The same separation was applied to scenario loading and prompt building.
The goal was to make the codebase easier to edit with confidence as scenario
coverage expands.