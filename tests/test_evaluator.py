import os
import shutil
import subprocess
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path

import pytest

import coderepair.evaluator as evaluator
from coderepair.docker_runner import CommandResult
from coderepair.evaluator import _protected_changes, evaluate_workspace
from coderepair.file_changes import FileChange, apply_file_changes
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


def task_with_snapshot_file(
    tmp_path: Path, relative_path: str, content: str = "original\n"
) -> tuple[Path, Workspace]:
    task_directory = tmp_path / "task"
    task_directory.mkdir()
    manifest = task_directory / "task.yaml"
    shutil.copy2(DEV_001_MANIFEST, manifest)
    snapshot = task_directory / "repo"
    shutil.copytree(DEV_001_SNAPSHOT, snapshot)
    (snapshot / relative_path).write_text(content, encoding="utf-8")
    return manifest, create_workspace(manifest, tmp_path / "workspace")


def forbid_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_run(*args: object, **kwargs: object) -> CommandResult:
        raise AssertionError("Docker must not run after a policy violation")

    monkeypatch.setattr(evaluator, "run_in_docker", unexpected_run)


def fake_successful_docker(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []

    def successful_run(
        workspace: Workspace,
        argv: Sequence[str],
        *,
        image: str,
        timeout_seconds: float,
        workspace_read_only: bool = False,
    ) -> CommandResult:
        del workspace, image, timeout_seconds
        assert workspace_read_only
        command = tuple(argv)
        calls.append(command)
        return CommandResult(command, 0, "", "", False, 0.01)

    monkeypatch.setattr(evaluator, "run_in_docker", successful_run)
    return calls


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
    assert not result.writable_paths_respected
    assert result.unauthorized_changes == ("tests/test_text_utils.py",)
    assert result.reproduction is None
    assert result.full_test is None
    assert result.lint is None


def test_modified_nonwritable_file_short_circuits_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, workspace = task_with_snapshot_file(tmp_path, "config.yaml")
    (workspace.root / "config.yaml").write_text("changed\n", encoding="utf-8")
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        manifest, workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert not result.success
    assert result.protected_paths_unchanged
    assert not result.writable_paths_respected
    assert result.unauthorized_changes == ("config.yaml",)
    assert result.reproduction is result.full_test is result.lint is None


def test_added_nonwritable_file_short_circuits_docker(
    dev_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    (dev_workspace.root / "config.yaml").write_text("added\n", encoding="utf-8")
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        DEV_001_MANIFEST, dev_workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert not result.writable_paths_respected
    assert result.unauthorized_changes == ("config.yaml",)
    assert result.reproduction is result.full_test is result.lint is None


def test_deleted_nonwritable_file_short_circuits_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, workspace = task_with_snapshot_file(tmp_path, "config.yaml")
    (workspace.root / "config.yaml").unlink()
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        manifest, workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert not result.writable_paths_respected
    assert result.unauthorized_changes == ("config.yaml",)
    assert result.reproduction is result.full_test is result.lint is None


def test_writable_modification_and_addition_reach_behavioral_checks(
    dev_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    (dev_workspace.root / "text_utils.py").write_text("# candidate\n", encoding="utf-8")
    (dev_workspace.root / "helper.py").write_text("# new\n", encoding="utf-8")
    calls = fake_successful_docker(monkeypatch)

    result = evaluate_workspace(
        DEV_001_MANIFEST, dev_workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert result.writable_paths_respected
    assert result.unauthorized_changes == ()
    assert result.success
    assert len(calls) == 3


def test_writable_deletion_is_policy_authorized(
    dev_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    (dev_workspace.root / "text_utils.py").unlink()
    calls = fake_successful_docker(monkeypatch)

    result = evaluate_workspace(
        DEV_001_MANIFEST, dev_workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert result.writable_paths_respected
    assert result.unauthorized_changes == ()
    assert len(calls) == 3


def test_structural_changes_are_policy_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, workspace = task_with_snapshot_file(tmp_path, "config.yaml")
    (workspace.root / "text_utils.py").unlink()
    (workspace.root / "text_utils.py").mkdir()
    (workspace.root / "empty_directory").mkdir()
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        manifest, workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert not result.writable_paths_respected
    assert result.unauthorized_changes == ("empty_directory", "text_utils.py")
    assert result.reproduction is None


def test_removed_empty_directory_is_policy_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_directory = tmp_path / "task"
    task_directory.mkdir()
    manifest = task_directory / "task.yaml"
    shutil.copy2(DEV_001_MANIFEST, manifest)
    snapshot = task_directory / "repo"
    shutil.copytree(DEV_001_SNAPSHOT, snapshot)
    (snapshot / "empty_directory").mkdir()
    workspace = create_workspace(manifest, tmp_path / "workspace")
    (workspace.root / "empty_directory").rmdir()
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        manifest, workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert result.unauthorized_changes == ("empty_directory",)


def test_violations_are_sorted_portable_and_separate_from_protected_changes(
    dev_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("z.yaml", "tests/new_test.py", "a.yaml"):
        (dev_workspace.root / name).write_text("new\n", encoding="utf-8")
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        DEV_001_MANIFEST, dev_workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert result.protected_changes == ("tests/new_test.py",)
    assert result.unauthorized_changes == (
        "a.yaml",
        "tests/new_test.py",
        "z.yaml",
    )
    assert str(dev_workspace.root) not in repr(result)
    assert str(dev_workspace.root.parent) not in repr(result)


def test_writable_symlink_is_rejected_without_following_it(
    dev_workspace: Workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    link = dev_workspace.root / "helper.py"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    original_read = Path.read_bytes

    def checked_read(path: Path) -> bytes:
        assert path != outside
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", checked_read)
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        DEV_001_MANIFEST, dev_workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert result.unauthorized_changes == ("helper.py",)
    assert result.reproduction is None
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_file_replaced_by_symlink_is_rejected(
    dev_workspace: Workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = dev_workspace.root / "tests" / "test_text_utils.py"
    target.unlink()
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    try:
        target.symlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        DEV_001_MANIFEST, dev_workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert result.unauthorized_changes == ("tests/test_text_utils.py",)
    assert result.protected_changes == ("tests/test_text_utils.py",)
    assert not result.protected_paths_unchanged
    assert result.reproduction is None


def test_hard_link_at_writable_path_is_rejected(
    dev_workspace: Workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    link = dev_workspace.root / "helper.py"
    try:
        link.hardlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"hard links are unavailable: {error}")
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        DEV_001_MANIFEST, dev_workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert result.unauthorized_changes == ("helper.py",)
    assert result.reproduction is None
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_junction_is_rejected_before_docker(
    dev_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name != "nt":
        pytest.skip("Windows directory junctions are unavailable")
    junction = dev_workspace.root / "tests_alias"
    try:
        creation = subprocess.run(
            [
                "cmd",
                "/c",
                "mklink",
                "/J",
                str(junction),
                str(dev_workspace.root / "tests"),
            ],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        pytest.skip(f"junction creation is unavailable: {error}")
    if creation.returncode != 0:
        pytest.skip(f"junction creation is unavailable: {creation.stderr.strip()}")
    assert junction.is_junction()
    forbid_docker(monkeypatch)

    result = evaluate_workspace(
        DEV_001_MANIFEST, dev_workspace, image=SANDBOX_IMAGE, timeout_seconds=10
    )

    assert result.unauthorized_changes == ("tests_alias",)
    assert result.reproduction is None


def test_unsafe_snapshot_entry_is_invalid_benchmark_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, workspace = task_with_snapshot_file(tmp_path, "config.yaml")
    outside = tmp_path / "outside.py"
    outside.write_text("outside\n", encoding="utf-8")
    try:
        (manifest.parent / "repo" / "linked.py").symlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    forbid_docker(monkeypatch)

    with pytest.raises(
        ValueError, match="snapshot contains an unsafe entry: linked.py"
    ):
        evaluate_workspace(
            manifest, workspace, image=SANDBOX_IMAGE, timeout_seconds=10
        )


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
    calls: list[tuple[tuple[str, ...], bool]] = []

    def successful_run(
        workspace: Workspace,
        argv: Sequence[str],
        *,
        image: str,
        timeout_seconds: float,
        workspace_read_only: bool = False,
    ) -> CommandResult:
        del workspace, image, timeout_seconds
        command = tuple(argv)
        calls.append((command, workspace_read_only))
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
    assert all(read_only for _, read_only in calls)


def test_all_evaluator_commands_use_read_only_workspace(
    dev_workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    read_only_flags: list[bool] = []

    def successful_run(
        workspace: Workspace,
        argv: Sequence[str],
        *,
        image: str,
        timeout_seconds: float,
        workspace_read_only: bool = False,
    ) -> CommandResult:
        del workspace, image, timeout_seconds
        read_only_flags.append(workspace_read_only)
        return CommandResult(tuple(argv), 0, "", "", False, 0.01)

    monkeypatch.setattr(evaluator, "run_in_docker", successful_run)
    result = evaluate_workspace(
        DEV_001_MANIFEST,
        dev_workspace,
        image=SANDBOX_IMAGE,
        timeout_seconds=10,
    )

    assert result.success
    assert read_only_flags == [True, True, True]


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
    apply_file_changes(
        dev_workspace,
        [
            FileChange(
                "text_utils.py",
                '"""Small text normalization helpers."""\n\n\n'
                "def normalize_name(value: str) -> str:\n"
                '    """Remove surrounding whitespace from a name."""\n'
                "    return value.strip()\n",
            )
        ],
    )

    result = evaluate_workspace(
        DEV_001_MANIFEST,
        dev_workspace,
        image=docker_image,
        timeout_seconds=30,
    )

    assert result.success
    assert result.protected_paths_unchanged
    assert result.writable_paths_respected
    assert result.unauthorized_changes == ()
    assert result.reproduction is not None
    assert result.reproduction.exit_code == 0
    assert result.full_test is not None
    assert result.full_test.exit_code == 0
    assert result.lint is not None
    assert result.lint.exit_code == 0


def test_candidate_cannot_modify_protected_test_during_evaluation(
    tmp_path: Path, docker_image: str
) -> None:
    task_directory = tmp_path / "task"
    task_directory.mkdir()
    shutil.copy2(DEV_001_MANIFEST, task_directory / "task.yaml")
    shutil.copytree(DEV_001_SNAPSHOT, task_directory / "repo")
    workspace = create_workspace(task_directory / "task.yaml", tmp_path / "workspace")
    protected_test = workspace.root / "tests" / "test_text_utils.py"
    original_content = protected_test.read_bytes()
    (workspace.root / "text_utils.py").write_text(
        "from pathlib import Path\n"
        "Path('tests/test_text_utils.py').write_text('def test_cheat(): pass\\n')\n"
        "def normalize_name(value: str) -> str:\n"
        "    return value.strip()\n",
        encoding="utf-8",
    )

    result = evaluate_workspace(
        task_directory / "task.yaml",
        workspace,
        image=docker_image,
        timeout_seconds=30,
    )

    assert not result.success
    assert result.protected_paths_unchanged
    assert result.reproduction is not None
    assert result.reproduction.exit_code != 0
    assert result.full_test is not None
    assert result.full_test.exit_code != 0
    assert protected_test.read_bytes() == original_content
    snapshot_test = task_directory / "repo" / "tests" / "test_text_utils.py"
    assert snapshot_test.read_bytes() == original_content
