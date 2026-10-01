"""Load packet values through the selected format backend."""

from pathlib import Path

from binary_backend import parse_binary
from sniffer import packet_format
from text_backend import parse_text


def load_packet(path: Path) -> dict[str, int]:
    payload = path.read_bytes()
    format_name = packet_format(payload)
    if format_name == "text":
        return parse_text(payload)
    return parse_binary(payload)
