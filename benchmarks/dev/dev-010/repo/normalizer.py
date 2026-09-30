"""Decode and normalize one parsed value."""


def normalize_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value.replace("\\;", ";").replace("\\\\", "\\").strip().casefold()
