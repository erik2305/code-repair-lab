"""Translate a compact cursor to a collection offset."""


def decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.startswith("p:") or not cursor[2:].isdecimal():
        raise ValueError("invalid page cursor")
    return int(cursor[2:])
