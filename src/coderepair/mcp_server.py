"""Workspace-bound MCP tools for controlled changes and trusted feedback."""

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from coderepair.docker_runner import (
    DOCKER_INFRASTRUCTURE_PREFIX,
    CommandResult,
    DockerInfrastructureError,
    run_in_docker,
)
from coderepair.file_changes import FileChange
from coderepair.file_changes import apply_file_changes as _apply_changes
from coderepair.path_policy import validate_workspace_path
from coderepair.workspace import Workspace

_MAX_READ_BYTES = 256 * 1024
_MAX_OUTPUT_BYTES = 32 * 1024
_TRUNCATION_MARKER = b"\n... [output truncated] ...\n"


@dataclass(frozen=True)
class ExecutionToolResult:
    """Bounded model-facing feedback from one trusted benchmark command."""

    configured: bool
    exit_code: int | None
    timed_out: bool
    duration_seconds: float | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool


def build_mcp_server(
    workspace: Workspace, *, image: str, timeout_seconds: float
) -> MCPServer:
    """Build an MCP server permanently bound to one workspace."""
    server = MCPServer("CodeRepair Lab workspace")

    @server.tool()
    def read_file(path: str) -> str:
        """Read one UTF-8 file from the workspace, including protected files."""
        try:
            return _read_workspace_file(workspace, path)
        except (ValueError, OSError) as error:
            raise ToolError(_safe_tool_error(error, workspace.root)) from None

    @server.tool()
    def apply_file_changes(changes: list[FileChange]) -> list[str]:
        """Replace or create allowed workspace text files."""
        if not changes:
            raise ToolError("changes must contain at least one file")
        try:
            _apply_changes(workspace, changes)
        except (ValueError, OSError) as error:
            raise ToolError(_safe_tool_error(error, workspace.root)) from None
        return [validate_workspace_path(change.path) for change in changes]

    def execute(argv: tuple[str, ...]) -> ExecutionToolResult:
        try:
            result = run_in_docker(
                workspace,
                argv,
                image=image,
                timeout_seconds=timeout_seconds,
                workspace_read_only=True,
            )
        except DockerInfrastructureError as error:
            raise ToolError(str(error)) from None
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise ToolError(_safe_execution_error(error)) from None
        return _execution_feedback(result, workspace.root)

    @server.tool()
    def run_reproduction() -> ExecutionToolResult:
        """Run the benchmark's trusted reproduction test read-only."""
        return execute(workspace.task.reproduction_test)

    @server.tool()
    def run_full_tests() -> ExecutionToolResult:
        """Run the benchmark's trusted full test suite read-only."""
        return execute(workspace.task.full_test)

    @server.tool()
    def run_lint() -> ExecutionToolResult:
        """Run the benchmark's trusted lint command, if configured."""
        if workspace.task.lint is None:
            return ExecutionToolResult(False, None, False, None, "", "", False, False)
        return execute(workspace.task.lint)

    return server


def raise_docker_tool_failure(tool: str, is_error: bool, content: str) -> None:
    """Trusted callers abort on the operational marker before model feedback."""
    if (
        tool in ("run_reproduction", "run_full_tests", "run_lint")
        and is_error
        and DOCKER_INFRASTRUCTURE_PREFIX in content
    ):
        diagnostic = content[content.index(DOCKER_INFRASTRUCTURE_PREFIX) :]
        raise DockerInfrastructureError(diagnostic)


def _execution_feedback(result: CommandResult, root: Path) -> ExecutionToolResult:
    stdout, stdout_truncated = _limited_output(_without_host_path(result.stdout, root))
    stderr, stderr_truncated = _limited_output(_without_host_path(result.stderr, root))
    return ExecutionToolResult(
        configured=True,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        duration_seconds=result.duration_seconds,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def _limited_output(value: str) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= _MAX_OUTPUT_BYTES:
        return value, False
    retained = _MAX_OUTPUT_BYTES - len(_TRUNCATION_MARKER)
    head = encoded[: retained // 2].decode("utf-8", errors="ignore")
    tail = encoded[-(retained - retained // 2) :].decode("utf-8", errors="ignore")
    return head + _TRUNCATION_MARKER.decode() + tail, True


def _without_host_path(value: str, root: Path) -> str:
    host_path = str(root)
    return value.replace(host_path, "/workspace").replace(
        host_path.replace("\\", "/"), "/workspace"
    )


def _safe_execution_error(
    error: OSError | ValueError | subprocess.SubprocessError,
) -> str:
    if isinstance(error, FileNotFoundError):
        return "Docker executable is unavailable"
    if isinstance(error, ValueError):
        return "Docker execution configuration is invalid"
    return "Docker execution failed before a command result was available"


def _read_workspace_file(workspace: Workspace, path: str) -> str:
    normalized = validate_workspace_path(path)
    root = workspace.root
    if (
        not root.is_absolute()
        or root.is_symlink()
        or root.is_junction()
        or not root.is_dir()
        or root.resolve() != root
    ):
        raise ValueError("workspace root must be a resolved absolute directory")

    target = root.joinpath(*PurePosixPath(normalized).parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError(f"file escapes workspace: {normalized}")

    parent = root
    for part in target.relative_to(root).parts[:-1]:
        directory = parent / part
        if directory.is_symlink() or directory.is_junction():
            raise ValueError(f"linked parent is not allowed: {normalized}")
        if not directory.is_dir():
            raise FileNotFoundError(f"parent directory does not exist: {normalized}")
        _require_exact_name(root, parent, directory)
        parent = directory

    if target.is_symlink() or target.is_junction():
        raise ValueError(f"linked file is not allowed: {normalized}")
    if not target.exists():
        raise FileNotFoundError(f"file does not exist: {normalized}")
    _require_exact_name(root, parent, target)
    if not target.is_file() or target.stat().st_nlink != 1:
        raise ValueError(f"file is not a regular workspace file: {normalized}")
    if target.stat().st_size > _MAX_READ_BYTES:
        raise ValueError(f"file exceeds read limit: {normalized}")

    with target.open("rb") as stream:
        content = stream.read(_MAX_READ_BYTES + 1)
    if len(content) > _MAX_READ_BYTES:
        raise ValueError(f"file exceeds read limit: {normalized}")
    return content.decode("utf-8")


def _require_exact_name(root: Path, parent: Path, path: Path) -> None:
    if not any(entry.name == path.name for entry in parent.iterdir()):
        relative = path.relative_to(root).as_posix()
        raise ValueError(f"filesystem path alias is not allowed: {relative}")


def _safe_tool_error(error: ValueError | OSError, root: Path) -> str:
    if isinstance(error, UnicodeError):
        return "file is not valid UTF-8"
    if isinstance(error, OSError) and (
        error.filename is not None
        or not isinstance(error, (FileNotFoundError, NotADirectoryError))
    ):
        return "filesystem access failed"

    message = str(error)
    root_text = str(root)
    for separator in ("/", "\\"):
        message = message.replace(root_text + separator, "")
    return message.replace(root_text, "workspace")
