"""Docker launch failures are operational, never model execution feedback."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import coderepair.docker_runner as docker_module
from coderepair.agent_generation import AgentStepResult
from coderepair.agent_loop import run_agentic_repair
from coderepair.agent_protocol import (
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
)
from coderepair.dev_v3_experiment import ARMS, run_scripted_repair
from coderepair.docker_runner import DockerInfrastructureError, run_in_docker
from coderepair.evaluator import evaluate_workspace
from coderepair.generation import GenerationResult, GenerationUsage
from coderepair.run_config import AgentLimits, RunConfig
from coderepair.workspace import create_workspace
from scripts import run_dev_v3_experiment as runner

ROOT = Path(__file__).resolve().parents[1]
CONFIG = RunConfig("fake", "medium", 4096, 60, 30, 100000, 200000, "sha256:pinned")


def manifest(task="dev-013"):
    return ROOT / "benchmarks/dev" / task / "task.yaml"


def docker_exit(monkeypatch, code, stderr="mount failed"):
    calls = []

    def run(argv, **options):
        calls.append(argv)
        return SimpleNamespace(returncode=code, stdout="", stderr=stderr)

    monkeypatch.setattr(docker_module.subprocess, "run", run)
    return calls


@pytest.mark.parametrize("exit_code", [1, 2, 3])
def test_normal_nonzero_exits_remain_command_results(tmp_path, monkeypatch, exit_code):
    workspace = create_workspace(manifest(), tmp_path / "workspace")
    docker_exit(monkeypatch, exit_code)
    result = run_in_docker(
        workspace, ("python",), image=CONFIG.docker_image, timeout_seconds=30
    )
    assert result.exit_code == exit_code
    assert not result.timed_out


def test_125_diagnostic_bounded_redacts_paths_and_secrets(tmp_path, monkeypatch):
    workspace = create_workspace(manifest(), tmp_path / "workspace")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-private-secret-value")
    stderr = (
        f"mount failed: '{workspace.root}' parent '{workspace.root.parent}' "
        "C:\\private\\file /outside/private Authorization: Bearer secret-value "
        "api_key=another-secret sk-private-secret-value " + "x" * 5000
    )
    docker_exit(monkeypatch, 125, stderr)
    with pytest.raises(DockerInfrastructureError) as failure:
        run_in_docker(
            workspace, ("python",), image=CONFIG.docker_image, timeout_seconds=30
        )
    message = str(failure.value)
    assert "mount failed" in message
    assert "truncated" in message
    assert len(message.encode()) < 2200
    for forbidden in (
        str(workspace.root),
        str(workspace.root.parent),
        "C:\\private",
        "/outside/private",
        "secret-value",
        "another-secret",
    ):
        assert forbidden not in message


@pytest.mark.parametrize(
    "action", [RunReproductionAction(), RunFullTestsAction(), RunLintAction()]
)
def test_agent_aborts_before_next_generation_on_125(tmp_path, monkeypatch, action):
    workspace = create_workspace(manifest(), tmp_path / "workspace")
    docker_calls = docker_exit(monkeypatch, 125)
    prompts = []

    def generator(prompt):
        prompts.append(prompt)
        return AgentStepResult(
            action, GenerationUsage(None, None, None), None, None, None
        )

    with pytest.raises(DockerInfrastructureError, match="mount failed"):
        run_agentic_repair(
            manifest(),
            workspace,
            generator=generator,
            config=CONFIG,
            limits=AgentLimits(8, 7, 200000),
        )
    assert len(prompts) == 1
    assert len(docker_calls) == 1
    assert "exit 125" not in prompts[0]


@pytest.mark.parametrize(
    "task,arm", [("dev-013", ARMS[1]), ("dev-013", ARMS[2]), ("dev-015", ARMS[2])]
)
def test_fixed_execution_evidence_aborts_on_125(tmp_path, monkeypatch, task, arm):
    workspace = create_workspace(manifest(task), tmp_path / "workspace")
    calls = docker_exit(monkeypatch, 125)
    prompts = []

    def generator(prompt):
        prompts.append(prompt)
        return GenerationResult((), GenerationUsage(None, None, None), None, None, None)

    with pytest.raises(DockerInfrastructureError, match="mount failed"):
        run_scripted_repair(
            manifest(task), workspace, generator=generator, config=CONFIG, arm=arm
        )
    assert len(prompts) == (0 if arm == ARMS[1] else 1)
    assert len(calls) == 1


def test_evaluator_125_is_not_unsuccessful_evaluation(tmp_path, monkeypatch):
    workspace = create_workspace(manifest(), tmp_path / "workspace")
    calls = docker_exit(monkeypatch, 125)
    with pytest.raises(DockerInfrastructureError):
        evaluate_workspace(
            manifest(), workspace, image=CONFIG.docker_image, timeout_seconds=30
        )
    assert len(calls) == 1


def test_preflight_uses_real_mounted_workspace_pinned_image_and_cleanup(monkeypatch):
    calls = docker_exit(monkeypatch, 0)
    original_run = docker_module.subprocess.run

    def run(argv, **kwargs):
        result = original_run(argv, **kwargs)
        assert argv[argv.index("--workdir") + 1] == "/workspace"
        assert "sha256:pinned" in argv
        mount = argv[argv.index("--mount") + 1]
        assert mount.endswith("target=/workspace,readonly")
        root = Path(mount.split("source=", 1)[1].split(",target=", 1)[0])
        assert root.is_dir()
        assert root.parent.parent == (ROOT / ".coderepair-tmp").resolve()
        assert (root / "loader.py").exists()
        run.root = root
        result.stdout = "coderepair-docker-preflight-ok\n"
        return result

    monkeypatch.setattr(docker_module.subprocess, "run", run)
    runner.docker_execution_preflight(manifest(), CONFIG)
    assert len(calls) == 1
    assert not run.root.exists()
    assert not run.root.parent.exists()


@pytest.mark.parametrize(
    "result",
    [
        SimpleNamespace(exit_code=1, timed_out=False, stdout=""),
        SimpleNamespace(exit_code=None, timed_out=True, stdout=""),
        SimpleNamespace(exit_code=0, timed_out=False, stdout="wrong"),
    ],
)
def test_preflight_requires_zero_exit_no_timeout_and_sentinel(monkeypatch, result):
    monkeypatch.setattr(runner, "run_in_docker", lambda *a, **kw: result)
    with pytest.raises(DockerInfrastructureError, match="preflight"):
        runner.docker_execution_preflight(manifest(), CONFIG)


@pytest.mark.parametrize("delay", ["-1", "nan", "inf", "-inf", "bad"])
def test_invalid_pacing_rejected_before_git_or_provider(tmp_path, monkeypatch, delay):
    monkeypatch.setattr(
        runner, "require_clean_git", lambda *a: pytest.fail("no Git yet")
    )
    with pytest.raises(SystemExit):
        runner.main(
            [
                "--purpose",
                "smoke",
                "--model",
                "fake",
                "--reasoning-effort",
                "medium",
                "--repetitions",
                "1",
                "--output",
                str(tmp_path / "out"),
                "--inter-attempt-delay-seconds",
                delay,
            ]
        )


def test_runner_preflight_failure_before_client_or_output(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "require_clean_git", lambda *a: "commit")
    monkeypatch.setattr(
        runner, "pin_docker_image", lambda c: (CONFIG, CONFIG.docker_image, ())
    )
    monkeypatch.setattr(
        runner, "OpenAI", lambda **kw: pytest.fail("no provider construction")
    )
    docker_exit(monkeypatch, 125, "mount unavailable")
    output = tmp_path / "out.jsonl"
    with pytest.raises(DockerInfrastructureError, match="mount unavailable"):
        runner.main(
            [
                "--purpose",
                "smoke",
                "--model",
                "fake",
                "--reasoning-effort",
                "medium",
                "--repetitions",
                "1",
                "--tasks",
                "dev-013",
                "--output",
                str(output),
            ]
        )
    assert not output.exists()


def test_successful_execution_probe_precedes_provider_construction(
    tmp_path, monkeypatch
):
    events = []
    monkeypatch.setattr(runner, "require_clean_git", lambda *a: "commit")

    def pin(config):
        events.append("pin")
        return CONFIG, CONFIG.docker_image, ()

    def execute(workspace, argv, **options):
        events.append("probe")
        assert workspace.root.is_dir()
        assert options["image"] == "sha256:pinned"
        assert options["workspace_read_only"] is True
        return SimpleNamespace(
            exit_code=0, timed_out=False, stdout="coderepair-docker-preflight-ok\n"
        )

    def client(**options):
        events.append("client")
        raise RuntimeError("test stops before any provider request")

    monkeypatch.setattr(runner, "pin_docker_image", pin)
    monkeypatch.setattr(runner, "run_in_docker", execute)
    monkeypatch.setattr(runner, "load_dotenv", lambda: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-fake-key")
    monkeypatch.setattr(runner, "OpenAI", client)
    with pytest.raises(RuntimeError, match="test stops"):
        runner.main(
            [
                "--purpose",
                "smoke",
                "--model",
                "fake",
                "--reasoning-effort",
                "medium",
                "--repetitions",
                "1",
                "--tasks",
                "dev-013",
                "--output",
                str(tmp_path / "out.jsonl"),
            ]
        )
    assert events == ["pin", "probe", "client"]
