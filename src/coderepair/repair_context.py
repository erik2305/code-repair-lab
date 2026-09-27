"""Deterministic, strategy-neutral context for a first repair inference."""

from dataclasses import dataclass
from pathlib import Path

from coderepair.workspace import Workspace


@dataclass(frozen=True, slots=True)
class ContextFile:
    """One complete UTF-8 repository file included in the initial context."""

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class InitialRepairContext:
    """Task and bounded repository information shared by repair strategies."""

    task_id: str
    bug_description: str
    writable_paths: tuple[str, ...]
    protected_paths: tuple[str, ...]
    repository_paths: tuple[str, ...]
    files: tuple[ContextFile, ...]
    omitted_paths: tuple[str, ...]


def build_initial_context(
    workspace: Workspace, *, max_file_bytes: int, max_total_bytes: int
) -> InitialRepairContext:
    """Inventory a workspace and include complete text files within byte limits."""
    for name, limit in (
        ("max_file_bytes", max_file_bytes),
        ("max_total_bytes", max_total_bytes),
    ):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError(f"{name} must be a positive integer")

    root = workspace.root
    if (
        not root.is_absolute()
        or root.is_symlink()
        or root.is_junction()
        or not root.is_dir()
        or root.resolve() != root
    ):
        raise ValueError("workspace root must be a resolved absolute directory")

    entries = sorted(
        _repository_entries(root), key=lambda path: path.relative_to(root).as_posix()
    )
    repository_paths: list[str] = []
    files: list[ContextFile] = []
    omitted_paths: list[str] = []
    used_bytes = 0

    for entry in entries:
        relative = entry.relative_to(root).as_posix()
        repository_paths.append(relative)
        if (
            entry.is_symlink()
            or entry.is_junction()
            or not entry.is_file()
            or not entry.resolve().is_relative_to(root)
        ):
            omitted_paths.append(relative)
            continue

        size = entry.stat().st_size
        if (
            size > max_file_bytes
            or used_bytes >= max_total_bytes
            or size > max_total_bytes - used_bytes
        ):
            omitted_paths.append(relative)
            continue

        content_bytes = entry.read_bytes()
        if (
            len(content_bytes) > max_file_bytes
            or len(content_bytes) > max_total_bytes - used_bytes
        ):
            omitted_paths.append(relative)
            continue
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            omitted_paths.append(relative)
            continue

        files.append(ContextFile(relative, content))
        used_bytes += len(content_bytes)

    return InitialRepairContext(
        task_id=workspace.task.id,
        bug_description=workspace.task.bug_description,
        writable_paths=workspace.task.writable_paths,
        protected_paths=workspace.task.protected_paths,
        repository_paths=tuple(repository_paths),
        files=tuple(files),
        omitted_paths=tuple(omitted_paths),
    )


def render_initial_context(context: InitialRepairContext) -> str:
    """Render the same initial information for any repair strategy."""
    sections = [
        "TASK\nid: " + context.task_id,
        "BUG DESCRIPTION\n" + context.bug_description.rstrip("\n"),
        _render_paths("WRITABLE PATHS", context.writable_paths),
        _render_paths("PROTECTED PATHS", context.protected_paths),
        _render_paths("REPOSITORY FILES", context.repository_paths),
    ]
    for file in context.files:
        language = "python" if file.path.endswith(".py") else "text"
        content = file.content
        if not content.endswith("\n"):
            content += "\n"
        sections.append(f"FILE: {file.path}\n```{language}\n{content}```")
    sections.append(_render_paths("OMITTED FILE CONTENTS", context.omitted_paths))
    return "\n\n".join(sections) + "\n"


def _repository_entries(root: Path) -> list[Path]:
    entries: list[Path] = []

    def visit(directory: Path) -> None:
        for entry in directory.iterdir():
            if entry.is_symlink() or entry.is_junction():
                entries.append(entry)
            elif entry.is_dir():
                visit(entry)
            else:
                entries.append(entry)

    visit(root)
    return entries


def _render_paths(heading: str, paths: tuple[str, ...]) -> str:
    return heading + "\n" + ("\n".join(f"- {path}" for path in paths) or "(none)")
