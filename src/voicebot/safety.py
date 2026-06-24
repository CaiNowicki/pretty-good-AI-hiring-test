"""Call safety checks.

The challenge requires calls to go only to the assessment number. Keep this
module dependency-free so it can be tested before telephony packages are set up.
"""

from __future__ import annotations

import re

from voicebot.constants import ALLOWED_DESTINATION


class UnsafeDestinationError(ValueError):
    """Raised when code attempts to dial a non-allowlisted destination."""


def normalize_e164(phone_number: str) -> str:
    """Normalize common phone formatting into a strict E.164-ish string."""

    compact = re.sub(r"[\s().-]", "", phone_number.strip())
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    if compact.isdigit() and len(compact) == 10:
        compact = "1" + compact
    if not compact.startswith("+"):
        compact = "+" + compact
    return compact


def validate_destination(phone_number: str) -> str:
    """Return the normalized destination or raise if it is not allowlisted."""

    normalized = normalize_e164(phone_number)
    if normalized != ALLOWED_DESTINATION:
        raise UnsafeDestinationError(
            f"Refusing to dial {normalized}. Only {ALLOWED_DESTINATION} is allowed."
        )
    return normalized
