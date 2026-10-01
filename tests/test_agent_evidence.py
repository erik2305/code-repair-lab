"""Offline evidence, occurrence, and shadow-replay checks."""

import json
from hashlib import sha256
from pathlib import Path

import pytest

import coderepair.agent_evidence as evidence_module
from coderepair.agent_evidence import (
    classify_iterative_occurrence,
    observation_evidence,
    patch_metadata,
    shadow_evaluate_prefixes,
)
from coderepair.agent_loop import AgentRunResult
from coderepair.agent_protocol import (
    AgentObservation,
    AgentTranscriptEntry,
    ApplyFileChangesAction,
    ReadFileAction,
    RunReproductionAction,
)
from coderepair.docker_runner import CommandResult
from coderepair.evaluator import EvaluationResult, workspace_state_sha256
from coderepair.file_changes import FileChange
from coderepair.workspace import create_workspace, destroy_workspace

MANIFEST = Path(__file__).resolve().parents[1] / "benchmarks/dev/dev-001/task.yaml"
SNAPSHOT_FILE = MANIFEST.parent / "repo/text_utils.py"


def _evaluation(success: bool) -> EvaluationResult:
    exit_code = 0 if success else 1
    command = CommandResult(("python",), exit_code, "", "", False, 0.1)
    return EvaluationResult(success, True, (), command, command, None)


def _entry(
    action: object,
    tool: str,
    content: str = "{}",
    *,
    is_error: bool = False,
) -> AgentTranscriptEntry:
    return AgentTranscriptEntry(action, AgentObservation(tool, content, is_error))


def _run(*entries: AgentTranscriptEntry, success: bool = True) -> AgentRunResult:
    return AgentRunResult((), entries, "finish", _evaluation(success), 1.0)


def test_patch_hash_is_order_stable_and_content_sensitive() -> None:
    first = (
        FileChange("b.py", "SECRET_B"),
        FileChange("a.py", "SECRET_A"),
    )
    same_reordered = tuple(reversed(first))
    changed = (FileChange("b.py", "DIFFERENT"), first[1])
    first_hash, entries = patch_metadata(first)

    assert first_hash == patch_metadata(same_reordered)[0]
    assert first_hash != patch_metadata(changed)[0]
    assert entries == [
        {"path": "a.py", "content_sha256": sha256(b"SECRET_A").hexdigest()},
        {"path": "b.py", "content_sha256": sha256(b"SECRET_B").hexdigest()},
    ]
    assert "SECRET" not in json.dumps(entries)


def test_execution_observation_preserves_failed_diagnostic_without_tool_error() -> None:
    content = json.dumps({"exit_code": 1, "timed_out": False, "stdout": "SECRET"})
    result = observation_evidence(
        _entry(RunReproductionAction(), "run_reproduction", content)
    )
    assert result["tool"] == "run_reproduction"
    assert result["is_error"] is False
    assert result["exit_code"] == 1
    assert result["timed_out"] is False
    assert result["observation_sha256"] == sha256(content.encode()).hexdigest()
    assert "SECRET" not in json.dumps(result)


def test_execution_observation_missing_details_remain_null() -> None:
    result = observation_evidence(
        _entry(
            RunReproductionAction(), "run_reproduction", "tool failed", is_error=True
        )
    )
    assert result["exit_code"] is None
    assert result["timed_out"] is None


def test_iterative_classifier_distinguishes_feedback_and_context() -> None:
    first = _entry(
        ApplyFileChangesAction((FileChange("text_utils.py", "first"),)),
        "apply_file_changes",
    )
    second = _entry(
        ApplyFileChangesAction((FileChange("text_utils.py", "second"),)),
        "apply_file_changes",
    )
    failing = _entry(
        RunReproductionAction(),
        "run_reproduction",
        '{"exit_code":1,"timed_out":false}',
    )
    read = _entry(ReadFileAction("text_utils.py"), "read_file", "source")

    assert classify_iterative_occurrence(_run(first)) == "tool_assisted_one_patch"
    assert (
        classify_iterative_occurrence(_run(first, failing, second))
        == "feedback_responsive_iteration"
    )
    assert (
        classify_iterative_occurrence(_run(first, read, second))
        == "context_refinement_iteration"
    )
    assert classify_iterative_occurrence(_run(first, failing, first)) == "none"
    assert (
        classify_iterative_occurrence(_run(first, failing, second, success=False))
        == "none"
    )
    tool_error = _entry(
        RunReproductionAction(), "run_reproduction", "failed", is_error=True
    )
    assert classify_iterative_occurrence(_run(first, tool_error, second)) == "none"


def test_workspace_hash_is_deterministic_and_fails_closed_on_link(
    tmp_path: Path,
) -> None:
    workspace = create_workspace(MANIFEST, tmp_path / "workspace")
    try:
        first = workspace_state_sha256(workspace.root)
        assert first == workspace_state_sha256(workspace.root)
        (workspace.root / "text_utils.py").write_text("changed", encoding="utf-8")
        assert workspace_state_sha256(workspace.root) != first
        link = workspace.root / "linked.py"
        try:
            link.symlink_to(tmp_path / "outside.py")
        except (NotImplementedError, OSError) as error:
            pytest.skip(f"symbolic links unavailable: {error}")
        with pytest.raises(ValueError, match="unsafe"):
            workspace_state_sha256(workspace.root)
    finally:
        destroy_workspace(workspace)


def test_shadow_replay_evaluates_cumulative_prefixes_off_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_before = SNAPSHOT_FILE.read_bytes()
    first = _entry(
        ApplyFileChangesAction((FileChange("text_utils.py", "first version"),)),
        "apply_file_changes",
    )
    second = _entry(
        ApplyFileChangesAction((FileChange("text_utils.py", "second version"),)),
        "apply_file_changes",
    )
    run = _run(first, second)
    observed_contents: list[str] = []

    def fake_evaluate(
        _manifest: Path, workspace: object, **_kwargs: object
    ) -> EvaluationResult:
        content = (workspace.root / "text_utils.py").read_text(encoding="utf-8")
        observed_contents.append(content)
        return _evaluation(content == "second version")

    monkeypatch.setattr(evidence_module, "evaluate_workspace", fake_evaluate)
    prefixes = shadow_evaluate_prefixes(
        MANIFEST, run, image="unused", timeout_seconds=1
    )

    assert [prefix.patch_index for prefix in prefixes] == [1, 2]
    assert [prefix.evaluation_success for prefix in prefixes] == [False, True]
    assert [prefix.reproduction_exit_code for prefix in prefixes] == [1, 0]
    assert prefixes[0].workspace_state_sha256 != prefixes[1].workspace_state_sha256
    assert observed_contents == ["first version", "second version"]
    assert run.transcript == (first, second)
    assert run.duration_seconds == 1.0
    assert SNAPSHOT_FILE.read_bytes() == source_before
