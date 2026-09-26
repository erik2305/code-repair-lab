"""Disposable workspaces for benchmark task snapshots."""

import shutil
from dataclasses import dataclass
from pathlib import Path

from coderepair.tasks import SnapshotSource, TaskSpec, load_task


@dataclass(frozen=True, slots=True)
class Workspace:
    """A mutable copy of a benchmark task repository."""

    task: TaskSpec
    root: Path


def create_workspace(task_manifest: Path, destination: Path) -> Workspace:
    """Copy a snapshot-backed task repository into *destination*."""
    task = load_task(task_manifest)
    if not isinstance(task.source, SnapshotSource):
        raise NotImplementedError(
            "Git-backed workspace materialization is not implemented"
        )

    task_directory = task_manifest.resolve().parent
    snapshot_path = task_directory / task.source.path
    snapshot = snapshot_path.resolve()
    if not snapshot.is_relative_to(task_directory):
        raise ValueError("snapshot source must remain within the task directory")
    if snapshot_path.is_symlink():
        raise ValueError("snapshot source must not be a symbolic link")
    if not snapshot.exists():
        raise FileNotFoundError(f"snapshot source directory does not exist: {snapshot}")
    if not snapshot.is_dir():
        raise NotADirectoryError(f"snapshot source is not a directory: {snapshot}")
    _reject_snapshot_symlinks(snapshot)

    resolved_destination = destination.resolve()
    if resolved_destination == snapshot or resolved_destination.is_relative_to(
        snapshot
    ):
        raise ValueError("workspace destination must be outside the snapshot")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"workspace destination already exists: {destination}")

    shutil.copytree(snapshot, resolved_destination)
    return Workspace(task=task, root=resolved_destination)


def destroy_workspace(workspace: Workspace) -> None:
    """Remove a materialized workspace tree."""
    shutil.rmtree(workspace.root)


def _reject_snapshot_symlinks(snapshot: Path) -> None:
    for path in snapshot.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"snapshot must not contain symbolic links: {path}")
