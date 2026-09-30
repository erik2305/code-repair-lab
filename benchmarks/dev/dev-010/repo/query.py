"""Parse field boundaries before decoding values."""

from normalizer import normalize_value
from tokenizer import split_fields


def parse_query(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for field in split_fields(text):
        if "=" not in field:
            raise ValueError("expected key=value field")
        key, value = field.split("=", 1)
        if not key.strip():
            raise ValueError("field key is empty")
        fields[key.strip().casefold()] = normalize_value(value)
    return fields
