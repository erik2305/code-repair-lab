"""Parse a complete text-format packet."""


def parse_text(packet: bytes) -> dict[str, int]:
    if not packet.startswith(b"TX|"):
        raise ValueError("text packet header missing")
    return {"value": int(packet[3:].decode("ascii"))}
