"""Controlled text-file changes in a disposable workspace."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from coderepair.path_policy import is_path_writable, validate_workspace_path
from coderepair.workspace import Workspace


@dataclass(frozen=True, slots=True)
class FileChange:
    """Replacement UTF-8 content for one workspace file."""

    path: str
    content: str


def apply_file_changes(workspace: Workspace, changes: Sequence[FileChange]) -> None:
    """Validate every target, then write the requested UTF-8 files."""
    root = workspace.root
    if (
        not root.is_absolute()
        or root.is_symlink()
        or root.is_junction()
        or not root.is_dir()
    ):
        raise ValueError("workspace root must be an absolute directory")
    if root.resolve() != root:
        raise ValueError("workspace root must be resolved")

    targets: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for change in changes:
        if not isinstance(change, FileChange) or not isinstance(change.content, str):
            raise ValueError("each change must have a string path and content")
        normalized = validate_workspace_path(change.path)
        if not is_path_writable(workspace.task, normalized):
            raise ValueError(f"workspace path is not writable: {normalized}")

        target = root.joinpath(*PurePosixPath(normalized).parts)
        target_key = os.path.normcase(str(target))
        if target_key in seen:
            raise ValueError(f"duplicate file change: {normalized}")
        seen.add(target_key)

        _validate_target(root, target)
        targets.append((target, change.content))

    for target, content in targets:
        target.write_text(content, encoding="utf-8")


def _validate_target(root: Path, target: Path) -> None:
    if not target.resolve().is_relative_to(root):
        raise ValueError(f"target escapes workspace: {target}")

    parent = root
    for part in target.relative_to(root).parts[:-1]:
        directory = parent / part
        if directory.is_symlink():
            raise ValueError(f"symbolic-link parent is not allowed: {directory}")
        if directory.is_junction():
            raise ValueError(f"junction parent is not allowed: {directory}")
        if not directory.is_dir():
            raise FileNotFoundError(f"parent directory does not exist: {directory}")
        _require_exact_name(parent, directory)
        parent = directory

    if target.is_symlink():
        raise ValueError(f"symbolic-link target is not allowed: {target}")
    if target.is_junction():
        raise ValueError(f"junction target is not allowed: {target}")
    if target.exists():
        _require_exact_name(parent, target)
        if not target.is_file():
            raise ValueError(f"target is not a regular file: {target}")
        if target.stat().st_nlink != 1:
            raise ValueError(f"hard-linked target is not allowed: {target}")


def _require_exact_name(parent: Path, path: Path) -> None:
    if not any(entry.name == path.name for entry in parent.iterdir()):
        raise ValueError(f"filesystem path alias is not allowed: {path}")
