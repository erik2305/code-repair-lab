"""Render poll deadlines for user-facing status text."""

from datetime import UTC, datetime


def format_poll_deadline(deadline: float) -> str:
    return datetime.fromtimestamp(deadline, UTC).strftime("%H:%M:%S UTC")
