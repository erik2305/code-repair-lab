"""Slice collections into pages and support cursor-based requests."""

from cursor_codec import decode_cursor
from page_limits import bounded_size


def window(items: list[str], offset: int, count: int) -> list[str]:
    if offset < 0 or count < 0:
        raise ValueError("offset and count must be non-negative")
    end = min(len(items) - 1, offset + count)
    return items[offset:end]


def page_from_cursor(
    items: list[str], cursor: str | None, requested_size: int
) -> list[str]:
    return window(items, decode_cursor(cursor), bounded_size(requested_size))
