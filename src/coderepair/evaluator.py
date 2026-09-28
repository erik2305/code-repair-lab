"""Independent evaluation of candidate benchmark workspaces."""

import stat
from dataclasses import dataclass, replace
from pathlib import Path

from coderepair.docker_runner import CommandResult, run_in_docker
from coderepair.path_policy import is_path_writable
from coderepair.tasks import SnapshotSource, TaskSpec, load_task
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
    writable_paths_respected: bool = True
    unauthorized_changes: tuple[str, ...] = ()


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
    snapshot_path = task_directory / task.source.path
    snapshot = snapshot_path.resolve()
    if not snapshot.is_relative_to(task_directory):
        raise ValueError("snapshot source must remain within the task directory")
    if snapshot_path.is_symlink() or snapshot_path.is_junction():
        raise ValueError("snapshot source must not be a link or junction")
    if not snapshot.exists():
        raise FileNotFoundError(f"snapshot source directory does not exist: {snapshot}")
    if not snapshot.is_dir():
        raise NotADirectoryError(f"snapshot source is not a directory: {snapshot}")

    original = _tree_inventory(snapshot, trusted_snapshot=True)
    candidate = _tree_inventory(workspace.root, trusted_snapshot=False)
    unauthorized_changes = _unauthorized_changes(task, original, candidate)
    # The protected glob comparison is safe only after excluding linked entries.
    protected_changes = (
        _protected_changes_from_inventory(task, original, candidate)
        if any(kind == "unsafe" for kind, _ in candidate.values())
        else _protected_changes(snapshot, workspace.root, task.protected_paths)
    )
    if protected_changes or unauthorized_changes:
        return EvaluationResult(
            success=False,
            protected_paths_unchanged=not protected_changes,
            protected_changes=protected_changes,
            reproduction=None,
            full_test=None,
            lint=None,
            writable_paths_respected=not unauthorized_changes,
            unauthorized_changes=unauthorized_changes,
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
        writable_paths_respected=True,
        unauthorized_changes=(),
    )


def _tree_inventory(
    root: Path, *, trusted_snapshot: bool
) -> dict[str, tuple[str, bytes | None]]:
    if (
        not root.is_absolute()
        or root.is_symlink()
        or root.is_junction()
        or not root.is_dir()
        or root.resolve() != root
    ):
        raise ValueError("repository root must be a resolved absolute directory")

    entries: dict[str, tuple[str, bytes | None]] = {}

    def visit(directory: Path) -> None:
        for entry in sorted(directory.iterdir(), key=lambda path: path.name):
            relative = entry.relative_to(root).as_posix()
            if entry.is_symlink() or entry.is_junction():
                kind = "unsafe"
            else:
                info = entry.lstat()
                if stat.S_ISDIR(info.st_mode):
                    kind = "directory"
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    kind = "file"
                else:
                    kind = "unsafe"

            if kind == "unsafe" and trusted_snapshot:
                raise ValueError(f"snapshot contains an unsafe entry: {relative}")
            entries[relative] = (
                kind,
                entry.read_bytes() if kind == "file" else None,
            )
            if kind == "directory":
                visit(entry)

    visit(root)
    return entries


def _unauthorized_changes(
    task: TaskSpec,
    original: dict[str, tuple[str, bytes | None]],
    candidate: dict[str, tuple[str, bytes | None]],
) -> tuple[str, ...]:
    changed: set[str] = set()
    for path in original.keys() | candidate.keys():
        before = original.get(path)
        after = candidate.get(path)
        if before == after:
            continue
        if (
            (before is not None and before[0] != "file")
            or (after is not None and after[0] != "file")
            or not is_path_writable(task, path)
        ):
            changed.add(path)
    return tuple(sorted(changed))


def _protected_changes_from_inventory(
    task: TaskSpec,
    original: dict[str, tuple[str, bytes | None]],
    candidate: dict[str, tuple[str, bytes | None]],
) -> tuple[str, ...]:
    # Avoid globbing through candidate links while retaining protected diagnostics.
    protected_task = replace(
        task, writable_paths=task.protected_paths, protected_paths=()
    )
    return tuple(
        sorted(
            path
            for path in original.keys() | candidate.keys()
            if original.get(path) != candidate.get(path)
            and is_path_writable(protected_task, path)
        )
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
