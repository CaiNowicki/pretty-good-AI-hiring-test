# Call 012 Review

Status: failed calibration/retry-only. Do not submit as final evidence.

Reason: the patient bot broke character and identified the call as a demo.

Evidence:

- `00:55` / `2026-06-24T20:58:27.095+00:00`: Patient Bot says, "I'm calling as part of this demo."
- `01:09` / `2026-06-24T20:58:41.977+00:00`: Patient Bot says, "I'd like to complete the demo intake."

Root-cause note:

The bridge answered short pre-goal fragments such as "for this demo" and
"Sounds good" with generic intake responses. It also needed to distinguish
isolated agent continuation fragments like "1987." from actual DOB questions
or confirmations like "1987?" Those generic responses let the model echo the
agent's demo framing instead of waiting for a full service-opening prompt and
staying in patient character.

Fix applied after this call:

- Treat `demo` as forbidden meta/disclosure language in turn prompts.
- Skip partial pre-goal fragments before creating a patient response, while
  still answering DOB questions and confirmation prompts with the exact
  scenario value.
- Keep "part of Pretty Good AI" as non-conversational opening context rather
  than patient identity or meta prompt content.
