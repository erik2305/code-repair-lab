"""Parse delay hints from the local polling service."""

SLOTS_PER_SECOND = 4


def parse_poll_hint(value: str) -> int:
    """Return a count of quarter-second scheduling slots."""
    prefix, separator, count = value.partition(":")
    if prefix != "slot" or not separator or not count.isdecimal():
        raise ValueError("invalid poll delay hint")
    return int(count)
