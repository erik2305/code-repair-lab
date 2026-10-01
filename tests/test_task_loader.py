from pathlib import Path

import pytest

from coderepair.tasks import GitSource, SnapshotSource, load_task

SNAPSHOT_MANIFEST = """
id: dev-001
source:
  type: snapshot
  path: repo
bug_description: Function normalize_name mishandles leading whitespace.
reproduction_test: [python, -m, pytest, tests/test_bug.py::test_leading_whitespace]
full_test: [python, -m, pytest]
lint: [ruff, check, .]
writable_paths: [src/**]
protected_paths: [tests/**]
"""


def write_manifest(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "task.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_snapshot_manifest(tmp_path: Path) -> None:
    task = load_task(write_manifest(tmp_path, SNAPSHOT_MANIFEST))

    assert task.id == "dev-001"
    assert task.source == SnapshotSource(type="snapshot", path="repo")
    assert task.reproduction_test == (
        "python",
        "-m",
        "pytest",
        "tests/test_bug.py::test_leading_whitespace",
    )
    assert task.full_test == ("python", "-m", "pytest")
    assert task.lint == ("ruff", "check", ".")
    assert task.writable_paths == ("src/**",)
    assert task.protected_paths == ("tests/**",)
    assert task.context_withheld_paths == ()


def test_context_withholding_is_sorted_and_normalized(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST + (
        "context_withheld_paths: [./z.py, tests/test_bug.py, a.py]\n"
    )
    task = load_task(write_manifest(tmp_path, manifest))
    assert task.context_withheld_paths == ("a.py", "tests/test_bug.py", "z.py")


@pytest.mark.parametrize(
    "value",
    ["../outside.py", "/absolute.py", "C:/outside.py", "C:\\outside.py", ""],
)
def test_rejects_unsafe_context_withheld_path(tmp_path: Path, value: str) -> None:
    manifest = SNAPSHOT_MANIFEST + f"context_withheld_paths: [{value!r}]\n"
    with pytest.raises(ValueError, match="context_withheld_paths"):
        load_task(write_manifest(tmp_path, manifest))


def test_rejects_duplicate_normalized_context_withheld_path(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST + "context_withheld_paths: [a.py, ./a.py]\n"
    with pytest.raises(ValueError, match="duplicate"):
        load_task(write_manifest(tmp_path, manifest))


def test_loads_git_manifest(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace(
        "type: snapshot\n  path: repo",
        "type: git\n  repo: https://github.com/example/project.git\n  commit: abc123",
    )

    task = load_task(write_manifest(tmp_path, manifest))

    assert task.source == GitSource(
        type="git",
        repo="https://github.com/example/project.git",
        commit="abc123",
    )


def test_lint_is_optional(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace("lint: [ruff, check, .]\n", "")

    task = load_task(write_manifest(tmp_path, manifest))

    assert task.lint is None


def test_rejects_missing_required_field(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace(
        "bug_description: Function normalize_name mishandles leading whitespace.\n",
        "",
    )

    with pytest.raises(ValueError, match="missing required field.*bug_description"):
        load_task(write_manifest(tmp_path, manifest))


def test_rejects_unsupported_source_type(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace("type: snapshot", "type: archive")

    with pytest.raises(ValueError, match="source.type"):
        load_task(write_manifest(tmp_path, manifest))


def test_rejects_command_string(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace(
        "full_test: [python, -m, pytest]", 'full_test: "python -m pytest"'
    )

    with pytest.raises(ValueError, match="full_test must be a list"):
        load_task(write_manifest(tmp_path, manifest))


def test_rejects_empty_command(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace(
        "reproduction_test: [python, -m, pytest, "
        "tests/test_bug.py::test_leading_whitespace]",
        "reproduction_test: []",
    )

    with pytest.raises(ValueError, match="reproduction_test must not be empty"):
        load_task(write_manifest(tmp_path, manifest))


def test_rejects_parent_path_traversal(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace(
        "writable_paths: [src/**]", "writable_paths: [../src/**]"
    )

    with pytest.raises(ValueError, match="parent traversal"):
        load_task(write_manifest(tmp_path, manifest))


def test_rejects_absolute_policy_path(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace(
        "protected_paths: [tests/**]", "protected_paths: [/etc/**]"
    )

    with pytest.raises(ValueError, match="relative path"):
        load_task(write_manifest(tmp_path, manifest))


def test_rejects_empty_writable_paths(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace(
        "writable_paths: [src/**]", "writable_paths: []"
    )

    with pytest.raises(ValueError, match="writable_paths must not be empty"):
        load_task(write_manifest(tmp_path, manifest))


def test_rejects_empty_protected_paths(tmp_path: Path) -> None:
    manifest = SNAPSHOT_MANIFEST.replace(
        "protected_paths: [tests/**]", "protected_paths: []"
    )

    with pytest.raises(ValueError, match="protected_paths must not be empty"):
        load_task(write_manifest(tmp_path, manifest))


def test_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    manifest = f"{SNAPSHOT_MANIFEST}typo: true\n"

    with pytest.raises(ValueError, match=r"unknown field\(s\): typo"):
        load_task(write_manifest(tmp_path, manifest))
