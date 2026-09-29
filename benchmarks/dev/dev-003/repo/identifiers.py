"""Canonical identifier rules shared by registry operations."""


def canonicalize_identifier(value: str) -> str:
    """Return a case-insensitive identifier without surrounding whitespace."""
    canonical = value.strip().casefold()
    if not canonical:
        raise ValueError("identifier must not be empty")
    return canonical
