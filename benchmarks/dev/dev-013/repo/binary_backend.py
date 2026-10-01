"""Parse a length-framed binary-format packet."""


def parse_binary(packet: bytes) -> dict[str, int]:
    if not packet.startswith(b"BX|"):
        raise ValueError("binary packet header missing")
    declared, separator, body = packet[3:].partition(b":")
    if not separator or not declared.isdigit():
        raise ValueError("invalid binary packet length")
    length = int(declared)
    if len(body) != length:
        raise ValueError(
            f"binary packet length mismatch: expected {length}, received {len(body)}"
        )
    return {"value": int(body.decode("ascii"))}
