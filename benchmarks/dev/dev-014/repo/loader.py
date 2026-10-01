"""Dispatch packet bytes to a format backend."""

from pathlib import Path

from binary_backend import parse_binary
from text_backend import parse_text


def load_packet(path: Path) -> dict[str, int]:
    payload = path.read_bytes()
    if payload.startswith(b"TX|"):
        return parse_text(payload)
    if payload.startswith(b"BX|"):
        return parse_binary(payload)
    raise ValueError("unrecognized packet header")
