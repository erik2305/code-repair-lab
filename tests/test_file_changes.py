import os
import subprocess
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from coderepair.file_changes import FileChange, apply_file_changes
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_001_DIRECTORY = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001"
DEV_001_MANIFEST = DEV_001_DIRECTORY / "task.yaml"
DEV_001_SNAPSHOT = DEV_001_DIRECTORY / "repo"


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Workspace]:
    result = create_workspace(DEV_001_MANIFEST, tmp_path / "workspace")
    yield result
    destroy_workspace(result)


def test_replaces_allowed_file_without_changing_snapshot(workspace: Workspace) -> None:
    source = DEV_001_SNAPSHOT / "text_utils.py"
    original = source.read_text(encoding="utf-8")

    apply_file_changes(workspace, [FileChange("text_utils.py", "changed\n")])

    assert (workspace.root / "text_utils.py").read_text(encoding="utf-8") == "changed\n"
    assert source.read_text(encoding="utf-8") == original


def test_creates_allowed_file_under_existing_parent(workspace: Workspace) -> None:
    apply_file_changes(workspace, [FileChange("new_module.py", "VALUE = 1\n")])

    assert (workspace.root / "new_module.py").read_text(encoding="utf-8") == (
        "VALUE = 1\n"
    )


def test_rejects_protected_file(workspace: Workspace) -> None:
    protected = workspace.root / "tests" / "test_text_utils.py"
    original = protected.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="not writable"):
        apply_file_changes(workspace, [FileChange("tests/test_text_utils.py", "")])

    assert protected.read_text(encoding="utf-8") == original


def test_forbidden_change_rejects_entire_batch(workspace: Workspace) -> None:
    allowed = workspace.root / "text_utils.py"
    protected = workspace.root / "tests" / "test_text_utils.py"
    original_allowed = allowed.read_bytes()
    original_protected = protected.read_bytes()

    with pytest.raises(ValueError, match="not writable"):
        apply_file_changes(
            workspace,
            [
                FileChange("text_utils.py", "changed\n"),
                FileChange("tests/test_text_utils.py", "changed\n"),
            ],
        )

    assert allowed.read_bytes() == original_allowed
    assert protected.read_bytes() == original_protected


def test_rejects_safe_but_non_writable_path(workspace: Workspace) -> None:
    with pytest.raises(ValueError, match="not writable"):
        apply_file_changes(workspace, [FileChange("README.md", "new\n")])

    assert not (workspace.root / "README.md").exists()


def test_rejects_parent_traversal(workspace: Workspace) -> None:
    outside = workspace.root.parent / "outside.py"

    with pytest.raises(ValueError, match="parent traversal"):
        apply_file_changes(workspace, [FileChange("../outside.py", "new\n")])

    assert not outside.exists()


def test_rejects_duplicate_normalized_target(workspace: Workspace) -> None:
    target = workspace.root / "text_utils.py"
    original = target.read_bytes()

    with pytest.raises(ValueError, match="duplicate"):
        apply_file_changes(
            workspace,
            [
                FileChange("text_utils.py", "first\n"),
                FileChange("./text_utils.py", "second\n"),
            ],
        )

    assert target.read_bytes() == original


def test_missing_parent_does_not_create_directories(workspace: Workspace) -> None:
    task = replace(workspace.task, writable_paths=("src/**",))
    permissive_workspace = Workspace(task=task, root=workspace.root)

    with pytest.raises(FileNotFoundError, match="parent directory"):
        apply_file_changes(
            permissive_workspace, [FileChange("src/module.py", "new\n")]
        )

    assert not (workspace.root / "src").exists()


def test_rejects_existing_symlink_target(
    workspace: Workspace, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("original\n", encoding="utf-8")
    link = workspace.root / "linked.py"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symbolic links are unavailable: {error}")

    with pytest.raises(ValueError, match="symbolic-link|escapes workspace"):
        apply_file_changes(workspace, [FileChange("linked.py", "changed\n")])

    assert outside.read_text(encoding="utf-8") == "original\n"


def test_rejects_junction_parent_aliasing_protected_tests(
    workspace: Workspace,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows directory junctions are unavailable")

    src = workspace.root / "src"
    src.mkdir()
    protected = workspace.root / "tests" / "test_text_utils.py"
    original = protected.read_bytes()
    junction = src / "tests_alias"
    try:
        creation = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(protected.parent)],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        pytest.skip(f"junction creation is unavailable: {error}")
    if creation.returncode != 0:
        pytest.skip(f"junction creation is unavailable: {creation.stderr.strip()}")
    assert junction.is_junction()

    task = replace(
        workspace.task,
        writable_paths=("src/**",),
        protected_paths=("tests/**",),
    )
    writable_workspace = Workspace(task=task, root=workspace.root)

    with pytest.raises(ValueError, match="junction parent"):
        apply_file_changes(
            writable_workspace,
            [FileChange("src/tests_alias/test_text_utils.py", "changed\n")],
        )

    assert protected.read_bytes() == original


def test_rejects_existing_hard_link(workspace: Workspace, tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("original\n", encoding="utf-8")
    original = outside.read_bytes()
    link = workspace.root / "linked.py"
    try:
        link.hardlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"hard links are unavailable: {error}")

    with pytest.raises(ValueError, match="hard-linked target"):
        apply_file_changes(workspace, [FileChange("linked.py", "changed\n")])

    assert link.read_bytes() == original
    assert outside.read_bytes() == original


def test_rejects_case_alias_of_protected_parent(workspace: Workspace) -> None:
    actual = workspace.root / "tests" / "test_text_utils.py"
    alias = workspace.root / "TESTS" / "test_text_utils.py"
    if not alias.exists() or not alias.samefile(actual):
        pytest.skip("workspace filesystem is case-sensitive")

    task = replace(workspace.task, writable_paths=("**",))
    permissive_workspace = Workspace(task=task, root=workspace.root)
    original = actual.read_bytes()

    with pytest.raises(ValueError, match="filesystem path alias"):
        apply_file_changes(
            permissive_workspace,
            [FileChange("TESTS/test_text_utils.py", "changed\n")],
        )

    assert actual.read_bytes() == original
