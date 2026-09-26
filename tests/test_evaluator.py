import shutil
import subprocess
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

import coderepair.evaluator as evaluator
from coderepair.docker_runner import CommandResult
from coderepair.evaluator import _protected_changes, evaluate_workspace
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_001_DIRECTORY = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001"
DEV_001_MANIFEST = DEV_001_DIRECTORY / "task.yaml"
DEV_001_SNAPSHOT = DEV_001_DIRECTORY / "repo"
SANDBOX_IMAGE = "coderepair-lab-sandbox:dev"


@pytest.fixture
def dev_workspace(tmp_path: Path) -> Iterator[Workspace]:
    workspace = create_workspace(DEV_001_MANIFEST, tmp_path / "workspace")
    yield workspace
    if workspace.root.exists():
        destroy_workspace(workspace)


def protected_changes(workspace: Workspace) -> tuple[str, ...]:
    return _protected_changes(
        DEV_001_SNAPSHOT,
        workspace.root,
        workspace.task.protected_paths,
    )


def test_unchanged_protected_paths(dev_workspace: Workspace) -> None:
    assert protected_changes(dev_workspace) == ()


def test_detects_modified_protected_file(dev_workspace: Workspace) -> None:
    test_file = dev_workspace.root / "tests" / "test_text_utils.py"
    test_file.write_text("modified\n", encoding="utf-8")

    assert protected_changes(dev_workspace) == ("tests/test_text_utils.py",)


def test_detects_deleted_protected_file(dev_workspace: Workspace) -> None:
    (dev_workspace.root / "tests" / "test_text_utils.py").unlink()

    assert protected_changes(dev_workspace) == ("tests/test_text_utils.py",)


def test_detects_added_protected_file(dev_workspace: Workspace) -> None:
    (dev_workspace.root / "tests" / "test_cheat.py").write_text(
        "# added\n", encoding="utf-8"
    )

    assert protected_changes(dev_workspace) == ("tests/test_cheat.py",)


def test_protected_tampering_short_circuits_commands(
    dev_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    test_file = dev_workspace.root / "tests" / "test_text_utils.py"
    test_file.write_text("modified\n", encoding="utf-8")

    def unexpected_run(*args: object, **kwargs: object) -> CommandResult:
        raise AssertionError("Docker command must not run after protected tampering")

    monkeypatch.setattr(evaluator, "run_in_docker", unexpected_run)
    result = evaluate_workspace(
        DEV_001_MANIFEST,
        dev_workspace,
        image=SANDBOX_IMAGE,
        timeout_seconds=10,
    )

    assert not result.success
    assert not result.protected_paths_unchanged
    assert result.protected_changes == ("tests/test_text_utils.py",)
    assert result.reproduction is None
    assert result.full_test is None
    assert result.lint is None


def test_rejects_workspace_for_different_task(dev_workspace: Workspace) -> None:
    mismatched_workspace = Workspace(
        task=replace(dev_workspace.task, id="different-task"),
        root=dev_workspace.root,
    )

    with pytest.raises(ValueError, match="does not match"):
        evaluate_workspace(
            DEV_001_MANIFEST,
            mismatched_workspace,
            image=SANDBOX_IMAGE,
            timeout_seconds=10,
        )


def test_lint_is_optional(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_directory = tmp_path / "task"
    snapshot = task_directory / "repo"
    (snapshot / "tests").mkdir(parents=True)
    (snapshot / "tests" / "test_example.py").write_text(
        "def test_example(): pass\n", encoding="utf-8"
    )
    manifest = task_directory / "task.yaml"
    manifest.write_text(
        """\
id: no-lint
source: {type: snapshot, path: repo}
bug_description: Temporary task without lint.
reproduction_test: [python, -m, pytest]
full_test: [python, -m, pytest]
writable_paths: ["*.py"]
protected_paths: [tests/**]
""",
        encoding="utf-8",
    )
    workspace = create_workspace(manifest, tmp_path / "workspace")
    calls: list[tuple[str, ...]] = []

    def successful_run(
        workspace: Workspace,
        argv: Sequence[str],
        *,
        image: str,
        timeout_seconds: float,
    ) -> CommandResult:
        del workspace, image, timeout_seconds
        command = tuple(argv)
        calls.append(command)
        return CommandResult(command, 0, "", "", False, 0.01)

    monkeypatch.setattr(evaluator, "run_in_docker", successful_run)
    result = evaluate_workspace(
        manifest,
        workspace,
        image=SANDBOX_IMAGE,
        timeout_seconds=10,
    )

    assert result.success
    assert result.lint is None
    assert len(calls) == 2


@pytest.fixture(scope="module")
def docker_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    try:
        daemon = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"Docker daemon is unavailable: {error}")
    if daemon.returncode != 0:
        pytest.skip("Docker daemon is unavailable")

    image = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if image.returncode != 0:
        pytest.skip(f"sandbox image is unavailable: {SANDBOX_IMAGE}")
    return SANDBOX_IMAGE


def test_original_dev_001_fails_evaluation(
    dev_workspace: Workspace, docker_image: str
) -> None:
    result = evaluate_workspace(
        DEV_001_MANIFEST,
        dev_workspace,
        image=docker_image,
        timeout_seconds=30,
    )

    assert not result.success
    assert result.protected_paths_unchanged
    assert result.reproduction is not None
    assert result.reproduction.exit_code != 0
    assert not result.reproduction.timed_out
    assert result.full_test is not None
    assert result.full_test.exit_code != 0
    assert not result.full_test.timed_out
    assert result.lint is not None
    assert result.lint.exit_code == 0
    assert not result.lint.timed_out


def test_repaired_dev_001_passes_evaluation(
    dev_workspace: Workspace, docker_image: str
) -> None:
    (dev_workspace.root / "text_utils.py").write_text(
        '"""Small text normalization helpers."""\n\n\n'
        "def normalize_name(value: str) -> str:\n"
        '    """Remove surrounding whitespace from a name."""\n'
        "    return value.strip()\n",
        encoding="utf-8",
    )

    result = evaluate_workspace(
        DEV_001_MANIFEST,
        dev_workspace,
        image=docker_image,
        timeout_seconds=30,
    )

    assert result.success
    assert result.protected_paths_unchanged
    assert result.reproduction is not None
    assert result.reproduction.exit_code == 0
    assert result.full_test is not None
    assert result.full_test.exit_code == 0
    assert result.lint is not None
    assert result.lint.exit_code == 0
