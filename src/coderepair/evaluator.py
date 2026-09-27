"""Independent evaluation of candidate benchmark workspaces."""

from dataclasses import dataclass
from pathlib import Path

from coderepair.docker_runner import CommandResult, run_in_docker
from coderepair.tasks import SnapshotSource, load_task
from coderepair.workspace import Workspace


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Results from the trusted checks for one candidate workspace."""

    success: bool
    protected_paths_unchanged: bool
    protected_changes: tuple[str, ...]
    reproduction: CommandResult | None
    full_test: CommandResult | None
    lint: CommandResult | None


def evaluate_workspace(
    task_manifest: Path,
    workspace: Workspace,
    *,
    image: str,
    timeout_seconds: float,
) -> EvaluationResult:
    """Evaluate a workspace using its immutable benchmark definition."""
    task = load_task(task_manifest)
    if task != workspace.task:
        raise ValueError("workspace task does not match the supplied task manifest")
    if not isinstance(task.source, SnapshotSource):
        raise NotImplementedError("Git-backed workspace evaluation is not implemented")

    task_directory = task_manifest.resolve().parent
    snapshot = (task_directory / task.source.path).resolve()
    if not snapshot.is_relative_to(task_directory):
        raise ValueError("snapshot source must remain within the task directory")
    if not snapshot.exists():
        raise FileNotFoundError(f"snapshot source directory does not exist: {snapshot}")
    if not snapshot.is_dir():
        raise NotADirectoryError(f"snapshot source is not a directory: {snapshot}")

    protected_changes = _protected_changes(
        snapshot, workspace.root, task.protected_paths
    )
    if protected_changes:
        return EvaluationResult(
            success=False,
            protected_paths_unchanged=False,
            protected_changes=protected_changes,
            reproduction=None,
            full_test=None,
            lint=None,
        )

    reproduction = run_in_docker(
        workspace,
        task.reproduction_test,
        image=image,
        timeout_seconds=timeout_seconds,
        workspace_read_only=True,
    )
    full_test = run_in_docker(
        workspace,
        task.full_test,
        image=image,
        timeout_seconds=timeout_seconds,
        workspace_read_only=True,
    )
    lint = (
        None
        if task.lint is None
        else run_in_docker(
            workspace,
            task.lint,
            image=image,
            timeout_seconds=timeout_seconds,
            workspace_read_only=True,
        )
    )

    success = (
        _command_passed(reproduction)
        and _command_passed(full_test)
        and (lint is None or _command_passed(lint))
    )
    return EvaluationResult(
        success=success,
        protected_paths_unchanged=True,
        protected_changes=(),
        reproduction=reproduction,
        full_test=full_test,
        lint=lint,
    )


def _protected_changes(
    snapshot: Path,
    workspace: Path,
    patterns: tuple[str, ...],
) -> tuple[str, ...]:
    original = _protected_files(snapshot, patterns)
    candidate = _protected_files(workspace, patterns)
    changed = {
        path
        for path in original.keys() | candidate.keys()
        if original.get(path) != candidate.get(path)
    }
    return tuple(sorted(changed))


def _protected_files(
    root: Path, patterns: tuple[str, ...]
) -> dict[str, tuple[str, bytes]]:
    files: dict[str, tuple[str, bytes]] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_symlink():
                files[path.relative_to(root).as_posix()] = ("symlink", b"")
            elif path.is_file():
                files[path.relative_to(root).as_posix()] = ("file", path.read_bytes())
    return files


def _command_passed(result: CommandResult) -> bool:
    return not result.timed_out and result.exit_code == 0
