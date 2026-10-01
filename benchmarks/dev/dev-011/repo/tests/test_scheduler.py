import json
from pathlib import Path

from scheduler import next_poll_at

CASE = Path(__file__).resolve().parents[1] / "fixtures" / "poll_case.json"


def test_hint_schedules_expected_poll() -> None:
    case = json.loads(CASE.read_text(encoding="utf-8"))
    assert next_poll_at(case["now"], case["hint"]) == case["expected"]


def test_missing_hint_keeps_current_deadline() -> None:
    assert next_poll_at(200.0, None) == 200.0
