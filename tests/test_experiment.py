"""Offline checks for paired-run ordering, provenance, and raw records."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from coderepair.agent_generation import AgentStepResult
from coderepair.agent_loop import AgentRunResult
from coderepair.agent_protocol import (
    AgentObservation,
    AgentTranscriptEntry,
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
)
from coderepair.baseline import SingleShotResult
from coderepair.docker_runner import CommandResult
from coderepair.evaluator import EvaluationResult
from coderepair.experiment import (
    ExperimentProvenance,
    agent_record,
    baseline_record,
    counterbalanced_order,
    inspect_docker_image,
    open_new_output,
    require_clean_git,
    serialize_action,
)
from coderepair.file_changes import FileChange
from coderepair.generation import GenerationResult, GenerationUsage
from coderepair.openrouter_generator import OpenRouterRepairGenerator
from coderepair.responses_schema import _RepairProposal
from coderepair.run_config import AgentLimits, RunConfig
from scripts import run_dev_experiment


def _config() -> RunConfig:
    return RunConfig(
        "logical-model", "medium", 4096, 60, 30, 100_000, 200_000, "sandbox:dev"
    )


def _limits() -> AgentLimits:
    return AgentLimits(6, 5, 100_000)


def _provenance() -> ExperimentProvenance:
    return ExperimentProvenance(
        "experiment-1", "abc123", "sha256:image", (), "3.13", "test-os"
    )


def _metadata() -> dict[str, object]:
    return dict(
        provenance=_provenance(),
        config=_config(),
        limits=_limits(),
        task_id="dev-001",
        repetition=1,
        position=1,
        started_utc="2026-09-29T00:00:00+00:00",
        finished_utc="2026-09-29T00:00:03+00:00",
        lint_configured=True,
    )


def _evaluation() -> EvaluationResult:
    command = CommandResult(("python",), 0, "secret output", "", False, 0.25)
    return EvaluationResult(True, True, (), command, command, command)


def test_counterbalanced_order_is_deterministic() -> None:
    assert [counterbalanced_order(index, 1) for index in range(4)] == [
        ("baseline", "agent"),
        ("agent", "baseline"),
        ("baseline", "agent"),
        ("agent", "baseline"),
    ]
    assert [counterbalanced_order(index, 2) for index in range(4)] == [
        ("agent", "baseline"),
        ("baseline", "agent"),
        ("agent", "baseline"),
        ("baseline", "agent"),
    ]


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (ReadFileAction("foo.py"), {"type": "read_file", "paths": ["foo.py"]}),
        (
            ApplyFileChangesAction(
                (FileChange("foo.py", "SECRET"), FileChange("bar.py", "SECRET"))
            ),
            {"type": "apply_file_changes", "paths": ["foo.py", "bar.py"]},
        ),
        (RunReproductionAction(), {"type": "run_reproduction", "paths": []}),
        (RunFullTestsAction(), {"type": "run_full_tests", "paths": []}),
        (RunLintAction(), {"type": "run_lint", "paths": []}),
        (FinishAction(), {"type": "finish", "paths": []}),
    ],
)
def test_serializes_only_action_type_and_paths(
    action: object, expected: object
) -> None:
    assert serialize_action(action) == expected
    assert "SECRET" not in json.dumps(serialize_action(action))


def test_unknown_action_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown agent action"):
        serialize_action(object())


def test_recorded_routing_policy_matches_actual_openrouter_request() -> None:
    client = Mock()
    client.with_options.return_value.responses.parse.return_value = SimpleNamespace(
        output_parsed=_RepairProposal.model_validate({"changes": []}),
        usage=None,
        model="returned-model",
    )
    generation = OpenRouterRepairGenerator(
        client,
        model="logical-model",
        reasoning_effort="medium",
        max_output_tokens=4096,
        request_timeout_seconds=60,
    )("repair this")
    record = baseline_record(
        SingleShotResult(generation, True, None, _evaluation(), 1.0),
        **_metadata(),
    )
    policy = record["routing_policy"]
    request = client.with_options.return_value.responses.parse.call_args.kwargs

    assert policy == {
        "cross_model_fallback": False,
        "same_model_provider_fallback": True,
        "require_parameters": True,
    }
    assert request["extra_body"]["provider"] == {
        "allow_fallbacks": policy["same_model_provider_fallback"],
        "require_parameters": policy["require_parameters"],
    }
    assert request["model"] == "logical-model"
    assert "models" not in request
    assert "models" not in request["extra_body"]


def test_unsafe_baseline_path_is_preserved_without_source_content() -> None:
    generation = GenerationResult(
        (FileChange("../outside.py", "SECRET SOURCE"),),
        GenerationUsage(None, None, None),
        None,
        "openrouter",
        "model",
    )
    record = baseline_record(
        SingleShotResult(generation, False, "not writable", None, 1.0),
        **_metadata(),
    )

    assert record["proposed_change_paths"] == ["../outside.py"]
    assert "SECRET SOURCE" not in json.dumps(record)


def test_unsafe_agent_paths_are_preserved_without_source_content() -> None:
    read = AgentStepResult(
        ReadFileAction("../outside.py"),
        GenerationUsage(None, None, None),
        None,
        "openrouter",
        "model",
    )
    apply = AgentStepResult(
        ApplyFileChangesAction((FileChange("../outside.py", "SECRET SOURCE"),)),
        GenerationUsage(None, None, None),
        None,
        "openrouter",
        "model",
    )
    record = agent_record(
        AgentRunResult((read, apply), (), "model_call_limit", _evaluation(), 1.0),
        **_metadata(),
    )

    assert [step["action_paths"] for step in record["generations"]] == [
        ["../outside.py"],
        ["../outside.py"],
    ]
    assert "SECRET SOURCE" not in json.dumps(record)


@pytest.mark.parametrize("cost", [None, 0.0])
def test_baseline_record_preserves_raw_telemetry_and_evaluator(
    cost: float | None,
) -> None:
    generation = GenerationResult(
        (FileChange("text_utils.py", "SECRET SOURCE"),),
        GenerationUsage(100, 20, 120),
        0.5,
        "openrouter",
        "returned-model",
        reported_cost_usd=cost,
        routed_provider="provider-a",
    )
    result = SingleShotResult(generation, True, None, _evaluation(), 3.0)
    record = baseline_record(result, **_metadata())

    assert record["success"] is True
    assert record["model_calls"] == 1
    assert record["tool_calls"] == 0
    assert record["input_tokens"] == 100
    assert record["reported_cost_usd"] == cost
    assert record["generation_reported_cost_usd"] == cost
    assert record["returned_model"] == "returned-model"
    assert record["requested_model"] == "logical-model"
    assert record["routed_provider"] == "provider-a"
    assert record["proposed_change_paths"] == ["text_utils.py"]
    assert record["evaluation_success"] is True
    assert record["writable_paths_respected"] is True
    assert record["protected_paths_unchanged"] is True
    assert record["reproduction"] == {
        "configured": True,
        "present": True,
        "exit_code": 0,
        "timed_out": False,
        "duration_seconds": 0.25,
    }
    assert record["lint"]["configured"] is True
    assert record["routing_policy"] == {
        "cross_model_fallback": False,
        "same_model_provider_fallback": True,
        "require_parameters": True,
    }
    assert record["configured_agent_limits"] == {
        "max_model_calls": 6,
        "max_tool_calls": 5,
        "max_transcript_bytes": 100_000,
    }
    assert record["agent_limits"] is None
    serialized = json.dumps(record, allow_nan=False)
    assert "SECRET SOURCE" not in serialized
    assert "secret output" not in serialized


def test_baseline_rejected_mutation_retains_missing_evaluation() -> None:
    generation = GenerationResult(
        (), GenerationUsage(None, None, None), None, None, None
    )
    result = SingleShotResult(generation, False, "not writable", None, 1.0)
    record = baseline_record(result, **_metadata())

    assert record["success"] is False
    assert record["evaluation_success"] is None
    assert record["reproduction"]["present"] is False
    assert record["reproduction"]["exit_code"] is None
    assert record["reported_cost_usd"] is None


def test_agent_record_preserves_generation_and_tool_provenance() -> None:
    steps = (
        AgentStepResult(
            ApplyFileChangesAction((FileChange("text_utils.py", "SECRET SOURCE"),)),
            GenerationUsage(100, 20, 120),
            0.5,
            "openrouter",
            "model-a",
            reported_cost_usd=0.0,
            routed_provider="provider-a",
        ),
        AgentStepResult(
            FinishAction(),
            GenerationUsage(None, None, None),
            None,
            "openrouter",
            "model-b",
            reported_cost_usd=None,
            routed_provider=None,
        ),
    )
    transcript = (
        AgentTranscriptEntry(
            steps[0].action,
            AgentObservation("apply_file_changes", "SECRET TOOL CONTENT", True),
        ),
    )
    result = AgentRunResult(steps, transcript, "finish", _evaluation(), 8.0)
    record = agent_record(result, **_metadata())

    assert record["termination_reason"] == "finish"
    assert record["model_calls"] == 2
    assert record["tool_calls"] == 1
    assert record["reported_cost_usd"] is None
    assert record["generations"][0] == {
        "step": 1,
        "action_type": "apply_file_changes",
        "action_paths": ["text_utils.py"],
        "gateway_provider": "openrouter",
        "returned_model": "model-a",
        "routed_provider": "provider-a",
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "reported_cost_usd": 0.0,
        "latency_seconds": 0.5,
    }
    assert record["generations"][1]["reported_cost_usd"] is None
    assert record["transcript"] == [
        {"step": 1, "tool": "apply_file_changes", "is_error": True}
    ]
    assert record["agent_limits"] == record["configured_agent_limits"]
    serialized = json.dumps(record, allow_nan=False)
    assert "SECRET SOURCE" not in serialized
    assert "SECRET TOOL CONTENT" not in serialized


def test_output_file_is_exclusive(tmp_path: Path) -> None:
    output = tmp_path / "results.jsonl"
    output.write_text("existing\n", encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        open_new_output(output)
    assert output.read_text(encoding="utf-8") == "existing\n"


def test_clean_git_guard_uses_commit_and_all_untracked_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(argv)
        stdout = "abc123\n" if "rev-parse" in argv else ""
        return SimpleNamespace(returncode=0, stdout=stdout)

    monkeypatch.setattr("coderepair.experiment.subprocess.run", fake_run)
    assert require_clean_git(Path(".")) == "abc123"
    assert calls == [
        ["git", "rev-parse", "--verify", "HEAD"],
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
    ]


def test_dirty_git_guard_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **_kwargs: object) -> SimpleNamespace:
        stdout = "abc123\n" if "rev-parse" in argv else "?? untracked.txt\n"
        return SimpleNamespace(returncode=0, stdout=stdout)

    monkeypatch.setattr("coderepair.experiment.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="commit or stash"):
        require_clean_git(Path("."))


def test_docker_image_id_and_digest_are_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(argv: list[str], **_kwargs: object) -> SimpleNamespace:
        assert argv == ["docker", "image", "inspect", "sandbox:dev"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                [{"Id": "sha256:image", "RepoDigests": ["repo@sha256:abc"]}]
            ),
        )

    monkeypatch.setattr("coderepair.experiment.subprocess.run", fake_run)
    assert inspect_docker_image("sandbox:dev") == ("sha256:image", ("repo@sha256:abc",))


def test_manual_runner_rejects_existing_output_before_client_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "existing.jsonl"
    output.write_text("original\n", encoding="utf-8")

    def unexpected_client(**_kwargs: object) -> None:
        pytest.fail("provider client must not be created")

    monkeypatch.setattr(run_dev_experiment, "OpenAI", unexpected_client)
    with pytest.raises(ValueError, match="already exists"):
        run_dev_experiment.main(["--model", "test-model", "--output", str(output)])
    assert output.read_text(encoding="utf-8") == "original\n"


def test_manual_runner_pairs_fresh_workspaces_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "TEST_SECRET_DO_NOT_PERSIST")
    monkeypatch.setattr(run_dev_experiment, "require_clean_git", lambda _root: "abc123")
    monkeypatch.setattr(
        run_dev_experiment,
        "inspect_docker_image",
        lambda _image: ("sha256:image", ()),
    )
    closed: list[bool] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(run_dev_experiment, "OpenAI", FakeClient)
    roots: list[Path] = []
    configs: list[RunConfig] = []

    def inspect_attempt(_manifest: Path, workspace: object, **kwargs: object) -> None:
        root = workspace.root
        assert not (root / "attempt-marker").exists()
        (root / "attempt-marker").write_text("used", encoding="utf-8")
        roots.append(root)
        configs.append(kwargs["config"])

    def fake_baseline(
        manifest: Path, workspace: object, **kwargs: object
    ) -> SingleShotResult:
        inspect_attempt(manifest, workspace, **kwargs)
        generation = GenerationResult(
            (), GenerationUsage(1, 1, 2), 0.1, "openrouter", "model"
        )
        return SingleShotResult(generation, True, None, _evaluation(), 1.0)

    def fake_agent(
        manifest: Path, workspace: object, **kwargs: object
    ) -> AgentRunResult:
        inspect_attempt(manifest, workspace, **kwargs)
        assert kwargs["limits"] is run_dev_experiment.AGENT_LIMITS
        step = AgentStepResult(
            FinishAction(), GenerationUsage(1, 1, 2), 0.1, "openrouter", "model"
        )
        return AgentRunResult((step,), (), "finish", _evaluation(), 1.0)

    monkeypatch.setattr(run_dev_experiment, "run_single_shot_baseline", fake_baseline)
    monkeypatch.setattr(run_dev_experiment, "run_agentic_repair", fake_agent)
    output = tmp_path / "results.jsonl"
    assert (
        run_dev_experiment.main(
            ["--model", "test-model", "--repetitions", "2", "--output", str(output)]
        )
        == 0
    )

    records = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 16
    assert len(set(roots)) == 16
    assert all(not root.exists() for root in roots)
    assert len({id(config) for config in configs}) == 1
    assert closed == [True]
    assert len({record["experiment_id"] for record in records}) == 1
    assert [record["strategy"] for record in records[:4]] == [
        "baseline",
        "agent",
        "agent",
        "baseline",
    ]
    assert [record["strategy"] for record in records[4:8]] == [
        "agent",
        "baseline",
        "baseline",
        "agent",
    ]
    assert all(record["docker_image_id"] == "sha256:image" for record in records)
    assert "TEST_SECRET_DO_NOT_PERSIST" not in output.read_text(encoding="utf-8")


def test_manual_runner_preserves_completed_record_on_later_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(run_dev_experiment, "require_clean_git", lambda _root: "abc123")
    monkeypatch.setattr(
        run_dev_experiment, "inspect_docker_image", lambda _image: ("sha256:image", ())
    )

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(run_dev_experiment, "OpenAI", FakeClient)
    generation = GenerationResult(
        (), GenerationUsage(1, 1, 2), 0.1, "openrouter", "model"
    )
    monkeypatch.setattr(
        run_dev_experiment,
        "run_single_shot_baseline",
        lambda *_args, **_kwargs: SingleShotResult(
            generation, True, None, _evaluation(), 1.0
        ),
    )

    def provider_failure(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(run_dev_experiment, "run_agentic_repair", provider_failure)
    output = tmp_path / "partial.jsonl"
    with pytest.raises(RuntimeError, match="provider unavailable"):
        run_dev_experiment.main(["--model", "test-model", "--output", str(output)])

    records = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["strategy"] == "baseline"
