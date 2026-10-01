"""Schedule a follow-up poll from a service delay hint."""

from display_time import format_poll_deadline
from poll_hint import parse_poll_hint


def next_poll_at(now: float, hint: str | None) -> float:
    if hint is None:
        return now
    delay = parse_poll_hint(hint)
    return now + delay


def describe_poll(deadline: float) -> str:
    return format_poll_deadline(deadline)
