import json
from pathlib import Path

from resolver import resolve

INDEX = Path(__file__).resolve().parents[1] / "fixtures" / "index.json"


def test_index_resolution_integration() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    assert resolve(index["releases"], index["constraint"]) == index["expected"], (
        "latest allowed version must use numeric ordering"
    )
