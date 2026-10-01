"""Typed benchmark task definitions."""

from dataclasses import dataclass
from typing import Literal, TypeAlias


@dataclass(frozen=True, slots=True)
class SnapshotSource:
    """A repository snapshot stored relative to the task manifest."""

    type: Literal["snapshot"]
    path: str


@dataclass(frozen=True, slots=True)
class GitSource:
    """A Git repository pinned to a commit."""

    type: Literal["git"]
    repo: str
    commit: str


TaskSource: TypeAlias = SnapshotSource | GitSource


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """The repository, bug, and evaluation criteria for a benchmark task."""

    id: str
    source: TaskSource
    bug_description: str
    reproduction_test: tuple[str, ...]
    full_test: tuple[str, ...]
    lint: tuple[str, ...] | None
    writable_paths: tuple[str, ...]
    protected_paths: tuple[str, ...]
    context_withheld_paths: tuple[str, ...] = ()
