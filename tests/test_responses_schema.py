"""Structured Responses contracts shared by the OpenRouter adapters."""

import pytest
from pydantic import ValidationError

from coderepair.agent_protocol import (
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
)
from coderepair.file_changes import FileChange
from coderepair.responses_schema import _AgentStep, _map_agent_action, _RepairProposal


def test_repair_schema_accepts_empty_and_ordered_changes() -> None:
    assert _RepairProposal.model_validate({"changes": []}).changes == []
    proposal = _RepairProposal.model_validate(
        {
            "changes": [
                {"path": "a.py", "content": "first"},
                {"path": "../outside.py", "content": "second"},
            ]
        }
    )
    assert [(item.path, item.content) for item in proposal.changes] == [
        ("a.py", "first"),
        ("../outside.py", "second"),
    ]


@pytest.mark.parametrize(
    "malformed",
    [
        {"changes": [], "usage": 100},
        {"changes": [{"path": "a.py", "content": "x", "extra": "no"}]},
        {"changes": [{"path": "a.py"}]},
        {"changes": [{"path": 1, "content": "x"}]},
        {"changes": "not a list"},
    ],
)
def test_repair_schema_rejects_malformed_fields(malformed: object) -> None:
    with pytest.raises(ValidationError):
        _RepairProposal.model_validate(malformed)


def test_agent_schema_has_strict_object_root_and_six_variants() -> None:
    schema = _AgentStep.model_json_schema()
    assert schema["type"] == "object"
    assert "anyOf" not in schema
    assert schema["additionalProperties"] is False
    assert len(schema["properties"]["action"]["anyOf"]) == 6
    assert all(
        definition["additionalProperties"] is False
        for definition in schema["$defs"].values()
    )


@pytest.mark.parametrize(
    "malformed",
    [
        {"action": {"type": "finish"}, "usage": 100},
        {"action": {"type": "finish", "success": True}},
        {"action": {"type": "read_file", "path": "a.py", "argv": []}},
        {
            "action": {
                "type": "apply_file_changes",
                "changes": [{"path": "a.py", "content": "x", "extra": "no"}],
            }
        },
        {"action": {"type": "run_command", "argv": ["echo"]}},
    ],
)
def test_agent_schema_rejects_extra_and_unknown_fields(malformed: object) -> None:
    with pytest.raises(ValidationError):
        _AgentStep.model_validate(malformed)


@pytest.mark.parametrize(
    "action,expected",
    [
        (
            {"type": "read_file", "path": "../outside.py"},
            ReadFileAction("../outside.py"),
        ),
        ({"type": "run_reproduction"}, RunReproductionAction()),
        ({"type": "run_full_tests"}, RunFullTestsAction()),
        ({"type": "run_lint"}, RunLintAction()),
        ({"type": "finish"}, FinishAction()),
        (
            {
                "type": "apply_file_changes",
                "changes": [
                    {"path": "a.py", "content": "first"},
                    {"path": "../outside.py", "content": "second"},
                ],
            },
            ApplyFileChangesAction(
                (FileChange("a.py", "first"), FileChange("../outside.py", "second"))
            ),
        ),
    ],
)
def test_agent_action_mapping(action: dict, expected: object) -> None:
    proposal = _AgentStep.model_validate({"action": action})
    assert _map_agent_action(proposal) == expected


def test_unexpected_parsed_action_fails_closed() -> None:
    class Unexpected:
        action = object()

    with pytest.raises(RuntimeError, match="unsupported parsed agent action"):
        _map_agent_action(Unexpected())  # type: ignore[arg-type]
