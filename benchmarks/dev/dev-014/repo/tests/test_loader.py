from pathlib import Path

from loader import load_packet

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample.packet"


def test_zero_field_in_fixture_is_retained() -> None:
    assert load_packet(FIXTURE) == {"retry_count": 0}


def test_nonzero_field_loads_from_either_backend(tmp_path: Path) -> None:
    packet = tmp_path / "packet.data"
    for header in (b"TX|", b"BX|"):
        packet.write_bytes(header + b"retry_count=2")
        assert load_packet(packet) == {"retry_count": 2}


def test_text_zero_is_also_retained(tmp_path: Path) -> None:
    packet = tmp_path / "packet.data"
    packet.write_bytes(b"TX|retry_count=0")
    assert load_packet(packet) == {"retry_count": 0}
