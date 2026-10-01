"""Decode a binary-format packet's single integer field."""

from normalize import normalize_fields


def parse_binary(packet: bytes) -> dict[str, int]:
    name, value = packet[3:].decode("ascii").strip().split("=", 1)
    return normalize_fields({name: int(value)})
