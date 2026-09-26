from pathlib import Path

import pytest

from coderepair.workspace import Workspace, create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_001_DIRECTORY = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001"
DEV_001_MANIFEST = DEV_001_DIRECTORY / "task.yaml"
DEV_001_SNAPSHOT = DEV_001_DIRECTORY / "repo"


def write_manifest(tmp_path: Path, source: str) -> Path:
    manifest = tmp_path / "task.yaml"
    manifest.write_text(
        f"""\
id: temporary-task
source:
{source}
bug_description: Temporary workspace test task.
reproduction_test: [python, -m, pytest, tests/test_bug.py]
full_test: [python, -m, pytest]
writable_paths: ["*.py"]
protected_paths: [tests/**]
""",
        encoding="utf-8",
    )
    return manifest


def create_symlink_or_skip(link: Path, target: Path, *, is_directory: bool) -> None:
    try:
        link.symlink_to(target, target_is_directory=is_directory)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symbolic links are unavailable: {error}")


def test_materializes_dev_001_at_requested_destination(tmp_path: Path) -> None:
    destination = tmp_path / "workspace"

    workspace = create_workspace(DEV_001_MANIFEST, destination)

    assert isinstance(workspace, Workspace)
    assert workspace.task.id == "dev-001"
    assert workspace.root == destination
    assert (workspace.root / "text_utils.py").is_file()
    assert (workspace.root / "tests" / "test_text_utils.py").is_file()
    assert not (workspace.root / "repo").exists()


def test_workspace_changes_do_not_modify_snapshot(tmp_path: Path) -> None:
    original = (DEV_001_SNAPSHOT / "text_utils.py").read_text(encoding="utf-8")
    workspace = create_workspace(DEV_001_MANIFEST, tmp_path / "workspace")

    (workspace.root / "text_utils.py").write_text("changed\n", encoding="utf-8")

    assert (DEV_001_SNAPSHOT / "text_utils.py").read_text(encoding="utf-8") == original


def test_destroy_removes_workspace_only(tmp_path: Path) -> None:
    workspace = create_workspace(DEV_001_MANIFEST, tmp_path / "workspace")

    destroy_workspace(workspace)

    assert not workspace.root.exists()
    assert (DEV_001_SNAPSHOT / "text_utils.py").is_file()


def test_relative_destination_has_stable_absolute_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    creation_directory = tmp_path / "creation"
    other_directory = tmp_path / "other"
    creation_directory.mkdir()
    other_directory.mkdir()
    monkeypatch.chdir(creation_directory)

    workspace = create_workspace(DEV_001_MANIFEST, Path("workspace"))

    created_root = creation_directory / "workspace"
    assert workspace.root == created_root.resolve()
    assert workspace.root.is_absolute()

    monkeypatch.chdir(other_directory)
    destroy_workspace(workspace)

    assert not created_root.exists()


def test_existing_destination_is_rejected(tmp_path: Path) -> None:
    destination = tmp_path / "workspace"
    destination.mkdir()

    with pytest.raises(FileExistsError, match="destination already exists"):
        create_workspace(DEV_001_MANIFEST, destination)


def test_missing_snapshot_directory_is_rejected(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path, "  type: snapshot\n  path: missing")

    with pytest.raises(FileNotFoundError, match="snapshot source directory"):
        create_workspace(manifest, tmp_path / "workspace")


def test_destination_inside_snapshot_is_rejected(tmp_path: Path) -> None:
    task_directory = tmp_path / "task"
    snapshot = task_directory / "repo"
    snapshot.mkdir(parents=True)
    source_file = snapshot / "module.py"
    source_file.write_text("VALUE = 1\n", encoding="utf-8")
    manifest = write_manifest(task_directory, "  type: snapshot\n  path: repo")

    with pytest.raises(ValueError, match="destination must be outside"):
        create_workspace(manifest, snapshot / "workspace")

    assert source_file.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert not (snapshot / "workspace").exists()


def test_snapshot_source_file_is_rejected(tmp_path: Path) -> None:
    task_directory = tmp_path / "task"
    task_directory.mkdir()
    (task_directory / "repo").write_text("not a directory\n", encoding="utf-8")
    manifest = write_manifest(task_directory, "  type: snapshot\n  path: repo")

    with pytest.raises(NotADirectoryError, match="snapshot source"):
        create_workspace(manifest, tmp_path / "workspace")


def test_snapshot_symlink_escape_is_rejected(tmp_path: Path) -> None:
    task_directory = tmp_path / "task"
    task_directory.mkdir()
    outside_snapshot = tmp_path / "outside"
    outside_snapshot.mkdir()
    create_symlink_or_skip(
        task_directory / "repo", outside_snapshot, is_directory=True
    )
    manifest = write_manifest(task_directory, "  type: snapshot\n  path: repo")

    with pytest.raises(ValueError, match="within the task directory"):
        create_workspace(manifest, tmp_path / "workspace")


def test_symlink_inside_snapshot_is_rejected(tmp_path: Path) -> None:
    task_directory = tmp_path / "task"
    snapshot = task_directory / "repo"
    snapshot.mkdir(parents=True)
    outside_file = tmp_path / "outside.py"
    outside_file.write_text("VALUE = 1\n", encoding="utf-8")
    create_symlink_or_skip(snapshot / "linked.py", outside_file, is_directory=False)
    manifest = write_manifest(task_directory, "  type: snapshot\n  path: repo")

    with pytest.raises(ValueError, match="must not contain symbolic links"):
        create_workspace(manifest, tmp_path / "workspace")


def test_git_workspace_materialization_is_not_implemented(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        "  type: git\n"
        "  repo: https://github.com/example/project.git\n"
        "  commit: abc123",
    )

    with pytest.raises(NotImplementedError, match="Git-backed"):
        create_workspace(manifest, tmp_path / "workspace")
