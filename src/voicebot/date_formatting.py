"""Helpers for patient-facing date wording."""

from __future__ import annotations

from datetime import date
import re


MONTH_NAMES = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def format_spoken_date(value: str) -> str:
    """Render ISO dates in natural spoken form, leaving other values unchanged."""

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return f"{MONTH_NAMES[parsed.month]} {parsed.day}, {parsed.year}"


def format_spoken_dates_in_text(text: str) -> str:
    """Render embedded ISO dates in natural spoken form."""

    return re.sub(
        r"\b\d{4}-\d{2}-\d{2}\b",
        lambda match: format_spoken_date(match.group(0)),
        text,
    )
