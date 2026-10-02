"""Network-free runner preflight, shared configuration and lifecycle regressions."""

import json
from dataclasses import replace
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

import coderepair.agent_evidence as shadow_module
import coderepair.agent_loop as agent_module
import coderepair.baseline as baseline_module
import coderepair.dev_v3_experiment as protocol
import coderepair.experiment as experiment_module
import coderepair.mcp_server as mcp_module
from coderepair.agent_generation import AgentStepResult
from coderepair.agent_protocol import (
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    RunReproductionAction,
)
from coderepair.docker_runner import CommandResult
from coderepair.evaluator import EvaluationResult
from coderepair.file_changes import FileChange
from coderepair.generation import GenerationResult, GenerationUsage
from scripts import run_dev_v3_experiment as runner

ROOT = Path(__file__).resolve().parents[1]


def arguments(output, *, task="dev-013", arms=None):
    values = [
        "--purpose",
        "smoke",
        "--model",
        "test-model",
        "--reasoning-effort",
        "medium",
        "--repetitions",
        "1",
        "--tasks",
        task,
        "--output",
        str(output),
    ]
    return values if arms is None else values + ["--arms", arms]


@pytest.fixture
def preflight(monkeypatch):
    events = []
    monkeypatch.setattr(runner, "load_dotenv", lambda: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "FAKE_SECRET")

    def git(root):
        events.append("git")
        return "committed"

    def pin(config):
        events.append("pin")
        assert config.docker_image == "coderepair-lab-sandbox:dev"
        return replace(config, docker_image="sha256:pinned"), "sha256:pinned", ()

    def unexpected_client(**kwargs):
        pytest.fail("provider client must not be constructed on preflight failure")

    monkeypatch.setattr(runner, "require_clean_git", git)
    monkeypatch.setattr(runner, "pin_docker_image", pin)
    monkeypatch.setattr(runner, "docker_execution_preflight", lambda *args: None)
    monkeypatch.setattr(runner, "OpenAI", unexpected_client)
    return events


@pytest.mark.parametrize("failure", ["git", "manifest", "context", "mapping", "pin"])
def test_preflight_failure_never_constructs_provider(
    tmp_path, monkeypatch, preflight, failure
):
    def fail(*args, **kwargs):
        raise RuntimeError(f"{failure} preflight failure")

    name = {
        "git": "require_clean_git",
        "manifest": "load_task",
        "context": "workspace_context",
        "mapping": "validate_mapping",
        "pin": "pin_docker_image",
    }[failure]
    monkeypatch.setattr(runner, name, fail)
    output = tmp_path / "result.jsonl"
    with pytest.raises(RuntimeError, match=failure):
        runner.main(arguments(output))
    assert not output.exists()


def test_bad_selection_fails_before_git_or_provider(tmp_path, preflight):
    with pytest.raises(ValueError, match="not applicable"):
        runner.main(
            arguments(tmp_path / "out.jsonl", task="dev-015", arms=protocol.ARMS[1])
        )
    assert preflight == []


def test_existing_output_is_never_overwritten_or_constructs_client(tmp_path, preflight):
    output = tmp_path / "result.jsonl"
    output.write_text("original", encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        runner.main(arguments(output))
    assert output.read_text() == "original"
    assert preflight == ["git", "pin"]


def test_missing_dependency_preflight_never_constructs_provider(
    tmp_path,
    monkeypatch,
    preflight,
):
    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(experiment_module, "version", missing)
    with pytest.raises(RuntimeError, match="dependency"):
        runner.main(arguments(tmp_path / "out.jsonl"))


def test_preflight_checks_all_manifests_before_contexts(
    tmp_path, monkeypatch, preflight
):
    events = []
    actual_load = runner.load_task
    actual_context = runner.workspace_context

    def load(path):
        events.append(("manifest", path.parent.name))
        return actual_load(path)

    def context(workspace, config):
        events.append(("context", workspace.task.id))
        return actual_context(workspace, config)

    monkeypatch.setattr(runner, "load_task", load)
    monkeypatch.setattr(runner, "workspace_context", context)
    # Existing output aborts after all other preflight, without a provider.
    output = tmp_path / "out.jsonl"
    output.touch()
    with pytest.raises(ValueError, match="already exists"):
        runner.main(arguments(output, task="dev-011,dev-013"))
    assert events == [
        ("manifest", "dev-011"),
        ("manifest", "dev-013"),
        ("context", "dev-011"),
        ("context", "dev-013"),
    ]


def test_all_arms_offline_pin_image_share_context_and_clean_fresh_copies(
    tmp_path,
    monkeypatch,
    preflight,
):
    events = preflight
    roots = []
    constructor_options = []
    snapshots = {
        path: path.read_bytes()
        for path in (ROOT / "benchmarks/dev/dev-013/repo").rglob("*")
        if path.is_file()
    }
    original_loader = snapshots[ROOT / "benchmarks/dev/dev-013/repo/loader.py"]
    loader = original_loader.decode() + "\n# GENERATED_SOURCE_SECRET\n"
    actual_create = runner.create_workspace
    actual_context = runner.workspace_context
    counts = {"repair": 0, "agent": 0, "docker": 0, "evaluation": 0}

    class Client:
        def __init__(self, **kwargs):
            events.append("client")
            assert events[:2] == ["git", "pin"]
            assert kwargs["api_key"] == "FAKE_SECRET"

        def close(self):
            events.append("close")

    def create(path, destination):
        workspace = actual_create(path, destination)
        assert (workspace.root / "loader.py").read_bytes() == original_loader
        roots.append(workspace.root)
        return workspace

    class Repair:
        def __init__(self, client, **options):
            constructor_options.append(options)
            self.calls = 0

        def __call__(self, prompt):
            counts["repair"] += 1
            self.calls += 1
            return GenerationResult(
                (FileChange("loader.py", loader),) if self.calls == 1 else (),
                GenerationUsage(100, 20, 120, 10, 5),
                0.5,
                "fake",
                "returned",
                0.01,
                "routed",
            )

    class Agent:
        def __init__(self, client, **options):
            constructor_options.append(options)
            self.actions = iter(
                (
                    ReadFileAction("loader.py"),
                    RunReproductionAction(),
                    ApplyFileChangesAction((FileChange("loader.py", loader),)),
                    FinishAction(),
                )
            )

        def __call__(self, prompt):
            counts["agent"] += 1
            return AgentStepResult(
                next(self.actions),
                GenerationUsage(1, 1, 2),
                0.1,
                "fake",
                "returned",
                0.01,
                "routed",
                protocol.sha256(prompt.encode()).hexdigest(),
            )

    def docker(workspace, argv, **options):
        counts["docker"] += 1
        assert options == {
            "image": "sha256:pinned",
            "timeout_seconds": 30,
            "workspace_read_only": True,
        }
        return CommandResult(tuple(argv), 1, "TOOL_OBSERVATION_SECRET", "", False, 0.1)

    def evaluate(manifest, workspace, **options):
        counts["evaluation"] += 1
        assert options == {"image": "sha256:pinned", "timeout_seconds": 30}
        command = CommandResult(("python",), 0, "EVALUATION_SECRET", "", False, 0.1)
        return EvaluationResult(True, True, (), command, command, command)

    monkeypatch.setattr(runner, "OpenAI", Client)
    monkeypatch.setattr(runner, "create_workspace", create)
    monkeypatch.setattr(runner, "OpenRouterRepairGenerator", Repair)
    monkeypatch.setattr(runner, "OpenRouterAgentStepGenerator", Agent)
    monkeypatch.setattr(mcp_module, "run_in_docker", docker)
    for module in (protocol, baseline_module, agent_module, shadow_module):
        monkeypatch.setattr(module, "evaluate_workspace", evaluate)
    output = tmp_path / "all.jsonl"
    timing_events = []

    def timestamp():
        timing_events.append("timestamp")
        return f"t{len(timing_events)}"

    def delay(seconds):
        rows = output.read_text("utf-8").splitlines()
        assert len(rows) == timing_events.count("delay") + 1
        assert seconds == 20
        timing_events.append("delay")

    monkeypatch.setattr(runner, "_utc_now", timestamp)
    monkeypatch.setattr(runner, "sleep", delay)
    assert runner.main(arguments(output) + ["--inter-attempt-delay-seconds", "20"]) == 0
    assert timing_events == [
        "timestamp",
        "timestamp",
        "delay",
        "timestamp",
        "timestamp",
        "delay",
        "timestamp",
        "timestamp",
        "delay",
        "timestamp",
        "timestamp",
    ]
    records = [json.loads(line) for line in output.read_text("utf-8").splitlines()]
    assert len(records) == 4
    assert [row["arm"] for row in records] == list(protocol.arm_order("dev-013", 1))
    assert all(row["inter_attempt_delay_seconds"] == 20 for row in records)
    assert all(row["strategy_duration_seconds"] < 20 for row in records)
    assert {row["arm"] for row in records} == set(protocol.ARMS)
    assert len({row["initial_context_sha256"] for row in records}) == 1
    assert len(roots) == 5  # one preflight and four independent live attempts
    assert len(set(roots)) == len(roots)
    assert all(not root.exists() for root in roots)
    assert counts == {"repair": 4, "agent": 4, "docker": 3, "evaluation": 7}
    assert (
        constructor_options
        == [
            {
                "model": "test-model",
                "reasoning_effort": "medium",
                "max_output_tokens": 4096,
                "request_timeout_seconds": 60,
            }
        ]
        * 4
    )
    assert events[-1] == "close"
    assert snapshots == {path: path.read_bytes() for path in snapshots}
    text = output.read_text("utf-8")
    for secret in (
        "GENERATED_SOURCE_SECRET",
        "TOOL_OBSERVATION_SECRET",
        "EVALUATION_SECRET",
        "FAKE_SECRET",
    ):
        assert secret not in text
    s0 = next(row for row in records if row["arm"] == protocol.ARMS[0])
    s2 = next(row for row in records if row["arm"] == protocol.ARMS[2])
    assert (
        s0["generations"][0]["prompt_sha256"] == s2["generations"][0]["prompt_sha256"]
    )
    for row in records:
        assert row["configured_docker_image"] == "coderepair-lab-sandbox:dev"
        assert row["docker_image_id"] == row["docker_image"] == "sha256:pinned"
        assert row["generations"]
        assert row["generations"][0]["prompt_sha256"]
        assert row["model_calls"] == (
            4
            if row["arm"] == protocol.ARMS[3]
            else 2
            if row["arm"] == protocol.ARMS[2]
            else 1
        )

    # An altered fresh context must abort before the next generator call.
    def drift(workspace, config):
        context = actual_context(workspace, config)
        if len(roots) > 6:
            return replace(context, bug_description="changed context")
        return context

    monkeypatch.setattr(runner, "workspace_context", drift)
    with pytest.raises(RuntimeError, match="context drift"):
        runner.main(arguments(tmp_path / "drift.jsonl", arms=protocol.ARMS[0]))
    assert counts["repair"] == 4


def test_completed_attempt_is_flushed_before_later_provider_failure(
    tmp_path,
    monkeypatch,
    preflight,
):
    output = tmp_path / "partial.jsonl"
    calls = []
    closed = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def close(self):
            closed.append(True)

    def generator(client, **options):
        def generate(prompt):
            calls.append(prompt)
            if len(calls) == 2:
                # First attempt must already be on disk, not merely buffered.
                rows = output.read_text("utf-8").splitlines()
                assert len(rows) == 1
                assert json.loads(rows[0])["task_id"] == "dev-011"
                raise RuntimeError("provider unavailable")
            return GenerationResult(
                (), GenerationUsage(None, None, None), None, None, None
            )

        return generate

    monkeypatch.setattr(runner, "OpenAI", Client)
    monkeypatch.setattr(runner, "OpenRouterRepairGenerator", generator)
    command = CommandResult(("python",), 1, "", "", False, 0.1)
    monkeypatch.setattr(
        baseline_module,
        "evaluate_workspace",
        lambda *a, **kw: EvaluationResult(False, True, (), command, command, command),
    )
    with pytest.raises(RuntimeError, match="provider unavailable"):
        runner.main(arguments(output, task="dev-011,dev-012", arms=protocol.ARMS[0]))
    assert len(calls) == 2
    assert closed == [True]
    assert len(output.read_text("utf-8").splitlines()) == 1
