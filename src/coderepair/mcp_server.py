"""Workspace-bound MCP tools for reading and controlled text changes."""

from pathlib import Path, PurePosixPath

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from coderepair.file_changes import FileChange
from coderepair.file_changes import apply_file_changes as _apply_changes
from coderepair.path_policy import validate_workspace_path
from coderepair.workspace import Workspace

_MAX_READ_BYTES = 256 * 1024


def build_mcp_server(workspace: Workspace) -> MCPServer:
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

    return server


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
