# A-06 Closed Hours Analysis

Watch for Branch B: the agent confirms a Saturday appointment.

If the agent confirms Saturday, the bot should double-check whether the office
is actually open on Saturdays. If the agent still confirms Saturday after that
double-check, flag the outcome as a potential bug. The expected correct behavior
is to decline Saturday, briefly explain the office is closed, and offer a useful
weekday morning alternative.
