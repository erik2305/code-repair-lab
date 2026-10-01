"""Identify the packet encoding from its transport header."""


def packet_format(payload: bytes) -> str:
    if payload.removeprefix(b"\xef\xbb\xbf").startswith(b"TX|"):
        return "text"
    if payload.startswith(b"BX|"):
        return "binary"
    raise ValueError("unrecognized packet header")
