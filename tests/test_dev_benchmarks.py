"""Trusted fixture checks; canonical repairs never enter benchmark snapshots."""

import shutil
import subprocess
from pathlib import Path

import pytest

from coderepair.docker_runner import run_in_docker
from coderepair.evaluator import evaluate_workspace
from coderepair.file_changes import FileChange, apply_file_changes
from coderepair.repair_context import build_initial_context
from coderepair.tasks import SnapshotSource, load_task
from coderepair.workspace import create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PROJECT_ROOT / "benchmarks" / "dev"
SANDBOX_IMAGE = "coderepair-lab-sandbox:dev"

# These reference edits are trusted test data, outside all benchmark snapshots.
CASES = (
    (
        "dev-002",
        "chunks.py",
        "tests/test_chunks.py::test_keeps_one_item_final_chunk",
        ("chunks.py",),
        "range(0, len(items) - size + 1, size)",
        "range(0, len(items), size)",
    ),
    (
        "dev-003",
        "registry.py",
        "tests/test_registry.py::test_lookup_accepts_combined_case_and_whitespace",
        ("identifiers.py", "registry.py"),
        "return self._entries[identifier]",
        "return self._entries[canonicalize_identifier(identifier)]",
    ),
    (
        "dev-004",
        "options.py",
        "tests/test_options.py::test_override_does_not_leak_into_later_call",
        ("options.py",),
        "options = DEFAULT_OPTIONS",
        "options = dict(DEFAULT_OPTIONS)",
    ),
)


def _manifest(task_id: str) -> Path:
    return BENCHMARK_ROOT / task_id / "task.yaml"


def _snapshot_files(task_id: str) -> dict[str, bytes]:
    root = BENCHMARK_ROOT / task_id / "repo"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize(
    ("task_id", "repair_path", "reproduction_node", "writable", "old", "new"),
    CASES,
)
def test_manifest_and_initial_context(
    tmp_path: Path,
    task_id: str,
    repair_path: str,
    reproduction_node: str,
    writable: tuple[str, ...],
    old: str,
    new: str,
) -> None:
    del repair_path, old, new
    manifest = _manifest(task_id)
    task = load_task(manifest)
    assert task.id == task_id
    assert task.source == SnapshotSource(type="snapshot", path="repo")
    assert task.reproduction_test == ("python", "-m", "pytest", reproduction_node)
    assert task.full_test == ("python", "-m", "pytest")
    assert task.lint == ("ruff", "check", "--ignore", "EXE002", ".")
    assert task.writable_paths == writable
    assert task.protected_paths == ("tests/**",)

    workspace = create_workspace(manifest, tmp_path / "workspace")
    try:
        context = build_initial_context(
            workspace, max_file_bytes=100_000, max_total_bytes=200_000
        )
        assert context.omitted_paths == ()
        assert context.repository_paths == tuple(
            sorted(_snapshot_files(task_id))
        )
        assert tuple(file.path for file in context.files) == context.repository_paths
    finally:
        destroy_workspace(workspace)


@pytest.fixture(scope="module")
def docker_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    try:
        daemon = subprocess.run(
            ["docker", "info"], capture_output=True, check=False, text=True, timeout=10
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


@pytest.mark.parametrize("task_id", [case[0] for case in CASES])
def test_original_snapshot_fails_tests_and_passes_lint(
    tmp_path: Path, docker_image: str, task_id: str
) -> None:
    manifest = _manifest(task_id)
    original = _snapshot_files(task_id)
    workspace = create_workspace(manifest, tmp_path / "workspace")
    try:
        results = (
            run_in_docker(
                workspace, command, image=docker_image, timeout_seconds=30,
                workspace_read_only=True,
            )
            for command in (
                workspace.task.reproduction_test,
                workspace.task.full_test,
                workspace.task.lint,
            )
        )
        reproduction, full_test, lint = results
        assert reproduction.exit_code == 1
        assert "1 failed" in reproduction.stdout
        assert full_test.exit_code == 1
        assert "failed" in full_test.stdout
        assert lint.exit_code == 0, lint.stdout
        assert not any(result.timed_out for result in (reproduction, full_test, lint))
    finally:
        destroy_workspace(workspace)
    assert _snapshot_files(task_id) == original


@pytest.mark.parametrize(
    ("task_id", "repair_path", "reproduction_node", "writable", "old", "new"),
    CASES,
)
def test_canonical_repair_passes_independent_evaluator(
    tmp_path: Path,
    docker_image: str,
    task_id: str,
    repair_path: str,
    reproduction_node: str,
    writable: tuple[str, ...],
    old: str,
    new: str,
) -> None:
    del reproduction_node, writable
    manifest = _manifest(task_id)
    original = _snapshot_files(task_id)
    workspace = create_workspace(manifest, tmp_path / "workspace")
    try:
        source = (workspace.root / repair_path).read_text(encoding="utf-8")
        assert source.count(old) == 1
        apply_file_changes(
            workspace, [FileChange(repair_path, source.replace(old, new))]
        )
        result = evaluate_workspace(
            manifest, workspace, image=docker_image, timeout_seconds=30
        )
        assert result.success, (
            result.reproduction.stdout if result.reproduction else None,
            result.full_test.stdout if result.full_test else None,
            result.lint.stdout if result.lint else None,
        )
        assert result.writable_paths_respected
        assert result.unauthorized_changes == ()
        assert result.protected_paths_unchanged
        assert result.protected_changes == ()
        assert result.reproduction is not None
        assert result.reproduction.exit_code == 0
        assert result.full_test is not None
        assert result.full_test.exit_code == 0
        assert result.lint is not None
        assert result.lint.exit_code == 0
    finally:
        destroy_workspace(workspace)
    assert _snapshot_files(task_id) == original
