# Product Observations

These notes come from manual product familiarization before building the caller bot. They should inform scenario design, but they are not final bug-report evidence until reproduced in submitted bot calls with transcript and recording.

## Manual Test Account Call

Observed flow:

- The agent called the user and began with standard identity verification questions.
- The agent guided the user toward scheduling a consultation.
- The user approved a `new patient consultation`.
- The agent asked whether the user wanted a specific provider or was open to anyone.
- The agent paused while searching for an opening.
- The user gave a deliberately broad and mildly difficult time window: `10 AM - 1 PM`.
- The agent found and booked an appointment, then confirmed the date.
- The agent instructed the user to bring ID and insurance card.
- The agent asked whether there was anything else it could help with.
- When the user said no, the agent confirmed the appointment again and ended the call.

## Takeaways

- The basic happy path appears functional: identity verification, new-patient consultation, provider flexibility, broad time window, booking, confirmation, and closing.
- The agent can handle at least one imprecise time-window request.
- Repetition may be a quality issue, especially around transferring to a scheduling agent and final appointment confirmation.
- There is likely value in testing whether repeated confirmation is consistently helpful or becomes confusing.

## Scenario Implications

- Include a baseline scheduling call, but do not spend too many final calls on simple happy paths.
- Probe provider preference handling: named provider, no preference, changed preference mid-call.
- Probe appointment-window negotiation: broad windows, unavailable windows, conflicting windows, and correction after the agent proposes a time.
- Probe repetition and closure: patient says no to additional help, asks if appointment is already confirmed, or becomes confused by repeated confirmations.
- Probe transfer language: whether the handoff to a scheduling agent causes repeated questions, lost context, or unnatural looping.
- Probe appointment-type classification: whether "new patient consultation" is preserved or followed by incompatible follow-up/routine-visit prompts.
- Probe transfer completion: whether an offered transfer actually connects, fails with explanation, or ends the call unexpectedly.
