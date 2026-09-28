from dataclasses import FrozenInstanceError, fields

import pytest

from coderepair.agent_protocol import (
    AgentObservation,
    AgentTranscriptEntry,
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
    tool_name_for_action,
)
from coderepair.file_changes import FileChange


class TupleSubclass(tuple):
    pass


@pytest.mark.parametrize(
    ("action", "tool"),
    [
        (ReadFileAction("text_utils.py"), "read_file"),
        (
            ApplyFileChangesAction((FileChange("text_utils.py", "x"),)),
            "apply_file_changes",
        ),
        (RunReproductionAction(), "run_reproduction"),
        (RunFullTestsAction(), "run_full_tests"),
        (RunLintAction(), "run_lint"),
    ],
)
def test_tool_actions_map_to_existing_mcp_names(action: object, tool: str) -> None:
    assert tool_name_for_action(action) == tool  # type: ignore[arg-type]
    observation = AgentObservation(tool, "", False)  # type: ignore[arg-type]
    assert AgentTranscriptEntry(action, observation).observation is observation


def test_finish_is_only_terminal_intent() -> None:
    finish = FinishAction()
    assert fields(finish) == ()
    assert fields(RunReproductionAction()) == ()
    assert fields(RunFullTestsAction()) == ()
    assert fields(RunLintAction()) == ()
    with pytest.raises(ValueError, match="executable tool"):
        tool_name_for_action(finish)  # type: ignore[arg-type]


@pytest.mark.parametrize("path", ["", "   ", None, 5])
def test_read_action_rejects_malformed_paths(path: object) -> None:
    with pytest.raises(ValueError, match="path"):
        ReadFileAction(path)  # type: ignore[arg-type]


def test_action_intent_does_not_enforce_path_policy() -> None:
    assert ReadFileAction("../outside.py").path == "../outside.py"
    change = FileChange("../outside.py", "untrusted proposal")
    assert ApplyFileChangesAction((change,)).changes == (change,)


def test_empty_and_valid_file_change_tuples_are_allowed() -> None:
    assert ApplyFileChangesAction(()).changes == ()
    changes = (FileChange("a.py", "a"), FileChange("b.py", "b"))
    assert ApplyFileChangesAction(changes).changes is changes


@pytest.mark.parametrize(
    "changes", [[], [FileChange("a.py", "a")], ("bad",), TupleSubclass()]
)
def test_change_action_rejects_malformed_collections(changes: object) -> None:
    with pytest.raises(ValueError, match="tuple of FileChange"):
        ApplyFileChangesAction(changes)  # type: ignore[arg-type]


def test_observation_accepts_empty_content_and_tool_error() -> None:
    assert AgentObservation("run_lint", "", True).is_error is True
    observation = AgentObservation("read_file", "file contents", False)
    assert observation.content == "file contents"


@pytest.mark.parametrize("tool", ["", "run_command", None, 3])
def test_observation_rejects_unknown_tool(tool: object) -> None:
    with pytest.raises(ValueError, match="known agent tool"):
        AgentObservation(tool, "", False)  # type: ignore[arg-type]


@pytest.mark.parametrize("content", [None, 4, b"bytes"])
def test_observation_rejects_non_string_content(content: object) -> None:
    with pytest.raises(ValueError, match="content"):
        AgentObservation("read_file", content, False)  # type: ignore[arg-type]


@pytest.mark.parametrize("is_error", [None, 0, 1, "false"])
def test_observation_requires_exact_bool_error_state(is_error: object) -> None:
    with pytest.raises(ValueError, match="is_error"):
        AgentObservation("read_file", "", is_error)  # type: ignore[arg-type]


def test_transcript_entry_requires_matching_tool() -> None:
    action = ReadFileAction("text_utils.py")
    observation = AgentObservation("read_file", "contents", False)
    assert AgentTranscriptEntry(action, observation).observation is observation

    with pytest.raises(ValueError, match="do not match"):
        AgentTranscriptEntry(
            action, AgentObservation("run_full_tests", "failed", False)
        )


def test_transcript_cannot_contain_finish_or_malformed_observation() -> None:
    observation = AgentObservation("read_file", "", False)
    with pytest.raises(ValueError, match="executable tool"):
        AgentTranscriptEntry(FinishAction(), observation)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="AgentObservation"):
        AgentTranscriptEntry(ReadFileAction("a.py"), "bad")  # type: ignore[arg-type]


def test_protocol_objects_are_frozen_and_slotted() -> None:
    action = ReadFileAction("a.py")
    observation = AgentObservation("read_file", "", False)
    entry = AgentTranscriptEntry(action, observation)
    for value in (action, observation, entry):
        assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        action.path = "b.py"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        observation.content = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entry.action = RunLintAction()  # type: ignore[misc]
