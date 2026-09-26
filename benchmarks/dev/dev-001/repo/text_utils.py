"""Small text normalization helpers."""


def normalize_name(value: str) -> str:
    """Remove surrounding whitespace from a name."""
    return value.strip(" ")
