"""Load and validate benchmark task manifests."""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml

from coderepair.tasks.models import GitSource, SnapshotSource, TaskSource, TaskSpec

_TOP_LEVEL_KEYS = {
    "id",
    "source",
    "bug_description",
    "reproduction_test",
    "full_test",
    "lint",
    "writable_paths",
    "protected_paths",
}
_REQUIRED_KEYS = _TOP_LEVEL_KEYS - {"lint"}


def load_task(path: Path) -> TaskSpec:
    """Load a YAML task manifest from *path* and validate its contract."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError(f"invalid YAML in task manifest: {error}") from error

    manifest = _mapping(data, "manifest")
    _validate_keys(manifest, _TOP_LEVEL_KEYS, _REQUIRED_KEYS, "manifest")

    return TaskSpec(
        id=_non_empty_string(manifest["id"], "id"),
        source=_source(manifest["source"]),
        bug_description=_non_empty_string(
            manifest["bug_description"], "bug_description"
        ),
        reproduction_test=_command(
            manifest["reproduction_test"], "reproduction_test"
        ),
        full_test=_command(manifest["full_test"], "full_test"),
        lint=None if "lint" not in manifest else _command(manifest["lint"], "lint"),
        writable_paths=_policy_paths(manifest["writable_paths"], "writable_paths"),
        protected_paths=_policy_paths(
            manifest["protected_paths"], "protected_paths"
        ),
    )


def _source(value: Any) -> TaskSource:
    source = _mapping(value, "source")
    source_type = source.get("type")

    if source_type == "snapshot":
        _validate_keys(source, {"type", "path"}, {"type", "path"}, "source")
        return SnapshotSource(
            type="snapshot",
            path=_portable_relative_path(source["path"], "source.path"),
        )
    if source_type == "git":
        keys = {"type", "repo", "commit"}
        _validate_keys(source, keys, keys, "source")
        return GitSource(
            type="git",
            repo=_non_empty_string(source["repo"], "source.repo"),
            commit=_non_empty_string(source["commit"], "source.commit"),
        )

    raise ValueError("source.type must be exactly 'snapshot' or 'git'")


def _command(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of command arguments")
    if not value:
        raise ValueError(f"{field} must not be empty")
    return tuple(
        _non_empty_string(argument, f"{field}[{index}]")
        for index, argument in enumerate(value)
    )


def _policy_paths(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of path patterns")
    if not value:
        raise ValueError(f"{field} must not be empty")

    paths = tuple(
        _portable_relative_path(pattern, f"{field}[{index}]")
        for index, pattern in enumerate(value)
    )
    return paths


def _portable_relative_path(value: Any, field: str) -> str:
    path = _non_empty_string(value, field)
    if "\\" in path:
        raise ValueError(f"{field} must use portable '/' separators")

    windows_path = PureWindowsPath(path)
    if PurePosixPath(path).is_absolute() or windows_path.is_absolute():
        raise ValueError(f"{field} must be a relative path")
    if windows_path.drive:
        raise ValueError(f"{field} must not contain a Windows drive")
    if ".." in PurePosixPath(path).parts:
        raise ValueError(f"{field} must not contain parent traversal")
    return path


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} keys must be strings")
    return value


def _non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _validate_keys(
    value: dict[str, Any],
    allowed: set[str],
    required: set[str],
    field: str,
) -> None:
    unknown = value.keys() - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"{field} contains unknown field(s): {names}")

    missing = required - value.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"{field} is missing required field(s): {names}")
