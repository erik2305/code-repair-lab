import json
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

import coderepair.agent_loop as agent_loop
import coderepair.mcp_server as mcp_server
from coderepair.agent_generation import AgentStepResult
from coderepair.agent_prompt import render_agent_transcript
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
from coderepair.docker_runner import CommandResult
from coderepair.evaluator import EvaluationResult
from coderepair.file_changes import FileChange
from coderepair.generation import GenerationUsage
from coderepair.repair_context import (
    InitialRepairContext,
    build_initial_context,
    render_initial_context,
)
from coderepair.run_config import AgentLimits, RunConfig
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001" / "task.yaml"
SNAPSHOT = MANIFEST.parent / "repo"
SANDBOX_IMAGE = "coderepair-lab-sandbox:dev"
CONFIG = RunConfig(
    model="fake-model",
    reasoning_effort="medium",
    max_output_tokens=512,
    request_timeout_seconds=12.5,
    evaluator_timeout_seconds=30,
    max_file_bytes=100_000,
    max_total_bytes=200_000,
    docker_image=SANDBOX_IMAGE,
)
LIMITS = AgentLimits(5, 5, 200_000)
CORRECT_REPAIR = (
    '"""Small text normalization helpers."""\n\n\n'
    "def normalize_name(value: str) -> str:\n"
    '    """Remove surrounding whitespace from a name."""\n'
    "    return value.strip()\n"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Workspace]:
    result = create_workspace(MANIFEST, tmp_path / "workspace")
    yield result
    destroy_workspace(result)


def step(action: object) -> AgentStepResult:
    return AgentStepResult(action, GenerationUsage(1, 1, 2), 0.5, "fake", "fake-model")


class SequenceGenerator:
    def __init__(self, *actions: object) -> None:
        self.actions = actions
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> AgentStepResult:
        self.prompts.append(prompt)
        return step(self.actions[len(self.prompts) - 1])


def fake_evaluator(monkeypatch: pytest.MonkeyPatch, *, success: bool = False) -> list:
    calls: list[tuple[Path, Workspace, str, float]] = []

    def evaluate(
        manifest: Path, workspace: Workspace, *, image: str, timeout_seconds: float
    ) -> EvaluationResult:
        calls.append((manifest, workspace, image, timeout_seconds))
        return EvaluationResult(success, True, (), None, None, None)

    monkeypatch.setattr(agent_loop, "evaluate_workspace", evaluate)
    return calls


def run(
    workspace: Workspace,
    generator: SequenceGenerator,
    *,
    limits: AgentLimits = LIMITS,
) -> agent_loop.AgentRunResult:
    return agent_loop.run_agentic_repair(
        MANIFEST, workspace, generator=generator, config=CONFIG, limits=limits
    )


def test_immediate_finish_and_first_call_fairness(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_evaluator(monkeypatch, success=False)
    original_source = (workspace.root / "text_utils.py").read_bytes()
    actual_build = agent_loop.build_initial_context
    context_builds = 0

    def tracked_build(
        bound_workspace: Workspace, *, max_file_bytes: int, max_total_bytes: int
    ) -> InitialRepairContext:
        nonlocal context_builds
        context_builds += 1
        assert bound_workspace is workspace
        assert (workspace.root / "text_utils.py").read_bytes() == original_source
        return actual_build(
            bound_workspace,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
        )

    monkeypatch.setattr(agent_loop, "build_initial_context", tracked_build)
    initial = render_initial_context(
        build_initial_context(
            workspace, max_file_bytes=100_000, max_total_bytes=200_000
        )
    )
    generator = SequenceGenerator(FinishAction())

    result = run(workspace, generator)

    assert result.termination_reason == "finish"
    assert context_builds == 1
    assert result.model_calls == 1
    assert result.tool_calls == 0
    assert result.transcript == ()
    assert result.generations[0].action == FinishAction()
    assert not result.success
    assert len(calls) == 1
    assert calls[0] == (MANIFEST, workspace, SANDBOX_IMAGE, 30)
    assert len(generator.prompts) == 1
    first = generator.prompts[0]
    assert first.count(initial) == 1
    assert "(no tool actions yet)" in first
    assert "Model calls remaining: 5" in first
    assert "Tool calls remaining: 5" in first
    assert (workspace.root / "text_utils.py").read_bytes() == original_source


def test_agent_duration_stops_after_final_evaluator(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    ticks = iter((3.0, 8.5))

    def clock() -> float:
        events.append("clock")
        return next(ticks)

    def evaluate(*args: object, **kwargs: object) -> EvaluationResult:
        events.append("evaluation")
        return EvaluationResult(False, True, (), None, None, None)

    def generator(prompt: str) -> AgentStepResult:
        events.append("generator")
        return step(FinishAction())

    monkeypatch.setattr(agent_loop, "perf_counter", clock)
    monkeypatch.setattr(agent_loop, "evaluate_workspace", evaluate)

    result = agent_loop.run_agentic_repair(
        MANIFEST, workspace, generator=generator, config=CONFIG, limits=LIMITS
    )

    assert events == ["clock", "generator", "evaluation", "clock"]
    assert result.duration_seconds == 5.5
    assert result.termination_reason == "finish"


def test_read_cycle_is_mcp_feedback_not_final_evaluator_feedback(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_evaluator(monkeypatch, success=True)
    generator = SequenceGenerator(ReadFileAction("text_utils.py"), FinishAction())

    result = run(workspace, generator)

    assert result.termination_reason == "finish"
    assert result.success
    assert result.model_calls == 2
    assert result.tool_calls == 1
    assert result.transcript[0].observation.tool == "read_file"
    assert not result.transcript[0].observation.is_error
    assert "value.strip" in result.transcript[0].observation.content
    assert result.transcript[0].observation.content in generator.prompts[1]
    assert "Model calls remaining: 4" in generator.prompts[1]
    assert "Tool calls remaining: 4" in generator.prompts[1]
    assert len(calls) == 1
    assert "EvaluationResult" not in generator.prompts[1]


def test_rejected_mutation_is_feedback_and_consumes_tool_budget(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_evaluator(monkeypatch)
    protected = workspace.root / "tests" / "test_text_utils.py"
    before = protected.read_bytes()
    generator = SequenceGenerator(
        ApplyFileChangesAction((FileChange("tests/test_text_utils.py", "bad"),)),
        RunLintAction(),
    )

    result = run(workspace, generator, limits=AgentLimits(3, 1, 200_000))

    assert result.termination_reason == "tool_call_limit"
    assert result.model_calls == 2
    assert result.tool_calls == 1
    assert len(result.transcript) == 1
    assert result.transcript[0].observation.is_error
    assert "not writable" in result.transcript[0].observation.content
    assert result.transcript[0].observation.content in generator.prompts[1]
    assert "Tool calls remaining: 0" in generator.prompts[1]
    assert protected.read_bytes() == before


def test_model_limit_and_remaining_values(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_evaluator(monkeypatch)
    generator = SequenceGenerator(*[ReadFileAction("text_utils.py")] * 3)

    result = run(workspace, generator, limits=AgentLimits(3, 5, 200_000))

    assert result.termination_reason == "model_call_limit"
    assert result.model_calls == 3
    assert result.tool_calls == 3
    assert len(calls) == 1
    assert [
        f"Model calls remaining: {remaining}" in prompt
        for remaining, prompt in zip((3, 2, 1), generator.prompts, strict=True)
    ] == [True, True, True]


def test_transcript_overflow_retains_entry_without_another_model_call(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_evaluator(monkeypatch)
    generator = SequenceGenerator(ReadFileAction("text_utils.py"))

    result = run(workspace, generator, limits=AgentLimits(3, 3, 1))

    assert result.termination_reason == "transcript_limit"
    assert result.model_calls == 1
    assert result.tool_calls == 1
    assert len(generator.prompts) == 1
    assert len(render_agent_transcript(result.transcript).encode("utf-8")) > 1
    assert len(calls) == 1


def test_transcript_budget_uses_utf8_bytes_and_allows_exact_limit(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_evaluator(monkeypatch)
    (workspace.root / "unicode.py").write_text("é", encoding="utf-8")
    expected = (
        AgentTranscriptEntry(
            ReadFileAction("unicode.py"),
            AgentObservation("read_file", '{"result":"é"}', False),
        ),
    )
    body = render_agent_transcript(expected)
    byte_size = len(body.encode("utf-8"))
    assert byte_size > len(body)

    generator = SequenceGenerator(ReadFileAction("unicode.py"), FinishAction())
    result = run(workspace, generator, limits=AgentLimits(3, 3, byte_size))

    assert result.termination_reason == "finish"
    assert result.transcript == expected
    assert len(generator.prompts) == 2

    too_small = SequenceGenerator(ReadFileAction("unicode.py"))
    overflow = run(workspace, too_small, limits=AgentLimits(3, 3, byte_size - 1))
    assert overflow.termination_reason == "transcript_limit"
    assert overflow.transcript == expected
    assert len(too_small.prompts) == 1


def test_all_five_action_mappings_use_real_mcp_boundary(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_evaluator(monkeypatch)
    docker_commands: list[tuple[tuple[str, ...], bool]] = []

    def fake_docker(
        bound_workspace: Workspace, argv: tuple[str, ...], *,
        image: str, timeout_seconds: float, workspace_read_only: bool,
    ) -> CommandResult:
        assert bound_workspace is workspace
        assert image == SANDBOX_IMAGE
        assert timeout_seconds == 30
        docker_commands.append((argv, workspace_read_only))
        return CommandResult(argv, 0, "ok", "", False, 0.1)

    monkeypatch.setattr(mcp_server, "run_in_docker", fake_docker)
    generator = SequenceGenerator(
        ReadFileAction("text_utils.py"),
        ApplyFileChangesAction((FileChange("text_utils.py", CORRECT_REPAIR),)),
        RunReproductionAction(), RunFullTestsAction(), RunLintAction(), FinishAction(),
    )

    result = run(workspace, generator, limits=AgentLimits(6, 5, 200_000))

    assert result.termination_reason == "finish"
    assert [entry.observation.tool for entry in result.transcript] == [
        "read_file", "apply_file_changes", "run_reproduction",
        "run_full_tests", "run_lint",
    ]
    assert json.loads(result.transcript[1].observation.content) == {
        "result": ["text_utils.py"]
    }
    assert (workspace.root / "text_utils.py").read_text(encoding="utf-8") == (
        CORRECT_REPAIR
    )
    assert docker_commands == [
        (command, True) for command in (
            workspace.task.reproduction_test,
            workspace.task.full_test,
            workspace.task.lint,
        )
    ]


def test_provider_failure_propagates_without_final_evaluation(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("final evaluator must not run")

    monkeypatch.setattr(agent_loop, "evaluate_workspace", unexpected)
    calls = 0

    def broken_generator(prompt: str) -> AgentStepResult:
        nonlocal calls
        calls += 1
        raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        agent_loop.run_agentic_repair(
            MANIFEST, workspace, generator=broken_generator,
            config=CONFIG, limits=LIMITS,
        )
    assert calls == 1


def test_invalid_generator_result_fails_without_evaluation(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("final evaluator must not run")

    monkeypatch.setattr(agent_loop, "evaluate_workspace", unexpected)
    with pytest.raises(ValueError, match="AgentStepResult"):
        agent_loop.run_agentic_repair(
            MANIFEST, workspace, generator=lambda prompt: FinishAction(),
            config=CONFIG, limits=LIMITS,
        )


def test_mcp_transport_exception_propagates_without_evaluation(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("final evaluator must not run")

    class BrokenClient:
        def __init__(self, server: object, *, raise_exceptions: bool) -> None:
            assert raise_exceptions

        async def __aenter__(self) -> "BrokenClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def call_tool(self, name: str, arguments: dict[str, object]) -> None:
            raise RuntimeError("MCP transport failed")

    monkeypatch.setattr(agent_loop, "evaluate_workspace", unexpected)
    monkeypatch.setattr(agent_loop, "Client", BrokenClient)
    with pytest.raises(RuntimeError, match="MCP transport failed"):
        run(workspace, SequenceGenerator(ReadFileAction("text_utils.py")))


def test_mismatched_manifest_fails_before_any_work(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    mismatched = replace(workspace, task=replace(workspace.task, id="other"))
    before = (workspace.root / "text_utils.py").read_bytes()

    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("no work should start for a mismatched task")

    monkeypatch.setattr(agent_loop, "build_initial_context", unexpected)
    monkeypatch.setattr(agent_loop, "build_mcp_server", unexpected)
    monkeypatch.setattr(agent_loop, "evaluate_workspace", unexpected)
    with pytest.raises(ValueError, match="does not match"):
        run(mismatched, unexpected)
    assert (workspace.root / "text_utils.py").read_bytes() == before


@pytest.fixture(scope="module")
def docker_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    try:
        daemon = subprocess.run(
            ["docker", "info"], capture_output=True, check=False, text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"Docker daemon is unavailable: {error}")
    if daemon.returncode != 0:
        pytest.skip("Docker daemon is unavailable")
    image = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        capture_output=True, check=False, text=True, timeout=10,
    )
    if image.returncode != 0:
        pytest.skip(f"sandbox image is unavailable: {SANDBOX_IMAGE}")
    return SANDBOX_IMAGE


def test_cumulative_repair_through_real_mcp_and_docker(
    workspace: Workspace, docker_image: str
) -> None:
    original = (SNAPSHOT / "text_utils.py").read_bytes()
    generator = SequenceGenerator(
        ApplyFileChangesAction((FileChange("text_utils.py", CORRECT_REPAIR),)),
        RunReproductionAction(),
        FinishAction(),
    )

    result = run(workspace, generator)

    assert result.termination_reason == "finish"
    assert result.success
    assert result.model_calls == 3
    assert result.tool_calls == 2
    assert result.transcript[1].observation.tool == "run_reproduction"
    assert json.loads(result.transcript[1].observation.content)["exit_code"] == 0
    assert result.evaluation.reproduction.exit_code == 0
    assert result.evaluation.full_test.exit_code == 0
    assert result.evaluation.lint.exit_code == 0
    assert (workspace.root / "text_utils.py").read_text(encoding="utf-8") == (
        CORRECT_REPAIR
    )
    assert (SNAPSHOT / "text_utils.py").read_bytes() == original
