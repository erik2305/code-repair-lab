"""Logical workspace path-policy checks."""

from fnmatch import fnmatchcase
from pathlib import PurePosixPath, PureWindowsPath

from coderepair.tasks import TaskSpec


def validate_workspace_path(path: str) -> str:
    """Return a normalized portable workspace path or raise ``ValueError``."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("workspace path must be a non-empty string")
    if "\\" in path:
        raise ValueError("workspace path must use portable '/' separators")

    posix_path = PurePosixPath(path)
    windows_path = PureWindowsPath(path)
    if posix_path.is_absolute() or windows_path.is_absolute():
        raise ValueError("workspace path must be relative")
    if windows_path.drive:
        raise ValueError("workspace path must not contain a Windows drive")
    if ".." in posix_path.parts:
        raise ValueError("workspace path must not contain parent traversal")

    normalized = posix_path.as_posix()
    if normalized == ".":
        raise ValueError("workspace path must identify an entry")
    return normalized


def is_path_writable(task: TaskSpec, path: str) -> bool:
    """Return whether *path* is safe, writable, and not protected."""
    try:
        normalized = validate_workspace_path(path)
    except ValueError:
        return False

    path_parts = PurePosixPath(normalized).parts
    if any(_matches_pattern(path_parts, pattern) for pattern in task.protected_paths):
        return False
    return any(
        _matches_pattern(path_parts, pattern) for pattern in task.writable_paths
    )


def _matches_pattern(path_parts: tuple[str, ...], pattern: str) -> bool:
    pattern_parts = PurePosixPath(pattern).parts

    def matches(path_index: int, pattern_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return path_index == len(path_parts)

        pattern_part = pattern_parts[pattern_index]
        if pattern_part == "**":
            return matches(path_index, pattern_index + 1) or (
                path_index < len(path_parts)
                and matches(path_index + 1, pattern_index)
            )
        return (
            path_index < len(path_parts)
            and fnmatchcase(path_parts[path_index], pattern_part)
            and matches(path_index + 1, pattern_index + 1)
        )

    return matches(0, 0)
