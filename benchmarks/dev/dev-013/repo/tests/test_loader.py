from pathlib import Path

from loader import load_packet

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample.packet"


def test_fixture_packet_loads() -> None:
    assert load_packet(FIXTURE) == {"value": 7}


def test_text_packet_loads(tmp_path: Path) -> None:
    packet = tmp_path / "text.packet"
    packet.write_bytes(b"TX|5")
    assert load_packet(packet) == {"value": 5}


def test_unpadded_binary_packet_loads(tmp_path: Path) -> None:
    packet = tmp_path / "binary.packet"
    packet.write_bytes(b"BX|1:6")
    assert load_packet(packet) == {"value": 6}
