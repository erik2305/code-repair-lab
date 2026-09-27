import asyncio
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from mcp import Client
from mcp.server import MCPServer

import coderepair.docker_runner as docker_runner
import coderepair.evaluator as evaluator
from coderepair.mcp_server import build_mcp_server
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_001_DIRECTORY = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001"
DEV_001_MANIFEST = DEV_001_DIRECTORY / "task.yaml"
DEV_001_SNAPSHOT = DEV_001_DIRECTORY / "repo"


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Workspace]:
    result = create_workspace(DEV_001_MANIFEST, tmp_path / "workspace")
    yield result
    destroy_workspace(result)


def test_tools_and_readable_files(workspace: Workspace) -> None:
    server = build_mcp_server(workspace)
    assert isinstance(server, MCPServer)

    async def check() -> None:
        async with Client(server, raise_exceptions=True) as client:
            listed = await client.list_tools()
            assert {tool.name for tool in listed.tools} == {
                "read_file",
                "apply_file_changes",
            }
            schemas = {tool.name: tool.input_schema for tool in listed.tools}
            assert set(schemas["read_file"]["properties"]) == {"path"}
            assert set(schemas["apply_file_changes"]["properties"]) == {"changes"}

            implementation = await client.call_tool(
                "read_file", {"path": "text_utils.py"}
            )
            assert not implementation.is_error
            assert "value.strip(\" \")" in implementation.structured_content["result"]

            protected = await client.call_tool(
                "read_file", {"path": "tests/test_text_utils.py"}
            )
            assert not protected.is_error
            assert "test_normalize_name" in protected.structured_content["result"]

    asyncio.run(check())


@pytest.mark.parametrize("path", ["../outside.py", "/etc/passwd", "C:/outside.py"])
def test_unsafe_read_is_tool_error(workspace: Workspace, path: str) -> None:
    async def check() -> None:
        async with Client(build_mcp_server(workspace), raise_exceptions=True) as client:
            result = await client.call_tool("read_file", {"path": path})
            assert result.is_error

    asyncio.run(check())


def test_read_rejects_missing_directory_binary_and_oversized_files(
    workspace: Workspace,
) -> None:
    (workspace.root / "invalid.py").write_bytes(b"\xff")
    (workspace.root / "large.py").write_bytes(b"x" * (256 * 1024 + 1))

    async def check() -> None:
        async with Client(build_mcp_server(workspace), raise_exceptions=True) as client:
            for path in ("missing.py", "tests", "invalid.py", "large.py"):
                result = await client.call_tool("read_file", {"path": path})
                assert result.is_error

    asyncio.run(check())


def test_allowed_mutation_uses_bound_workspace(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = (DEV_001_SNAPSHOT / "text_utils.py").read_bytes()

    def unexpected_execution(*args: object, **kwargs: object) -> None:
        raise AssertionError("MCP file tools must not execute benchmark commands")

    monkeypatch.setattr(docker_runner, "run_in_docker", unexpected_execution)
    monkeypatch.setattr(evaluator, "evaluate_workspace", unexpected_execution)

    async def check() -> None:
        async with Client(build_mcp_server(workspace), raise_exceptions=True) as client:
            result = await client.call_tool(
                "apply_file_changes",
                {"changes": [{"path": "text_utils.py", "content": "changed\n"}]},
            )
            assert not result.is_error
            assert result.structured_content["result"] == ["text_utils.py"]

            read_back = await client.call_tool(
                "read_file", {"path": "text_utils.py"}
            )
            assert not read_back.is_error
            assert read_back.structured_content["result"] == (
                workspace.root / "text_utils.py"
            ).read_bytes().decode("utf-8")

    asyncio.run(check())
    assert (workspace.root / "text_utils.py").read_text(encoding="utf-8") == "changed\n"
    assert (DEV_001_SNAPSHOT / "text_utils.py").read_bytes() == original


def test_protected_mutation_is_tool_error(workspace: Workspace) -> None:
    protected = workspace.root / "tests" / "test_text_utils.py"
    original = protected.read_bytes()

    async def check() -> None:
        async with Client(build_mcp_server(workspace), raise_exceptions=True) as client:
            result = await client.call_tool(
                "apply_file_changes",
                {"changes": [{"path": "tests/test_text_utils.py", "content": ""}]},
            )
            assert result.is_error

    asyncio.run(check())
    assert protected.read_bytes() == original


def test_invalid_multifile_mutation_changes_nothing(workspace: Workspace) -> None:
    allowed = workspace.root / "text_utils.py"
    protected = workspace.root / "tests" / "test_text_utils.py"
    original_allowed = allowed.read_bytes()
    original_protected = protected.read_bytes()

    async def check() -> None:
        async with Client(build_mcp_server(workspace), raise_exceptions=True) as client:
            result = await client.call_tool(
                "apply_file_changes",
                {
                    "changes": [
                        {"path": "text_utils.py", "content": "changed\n"},
                        {"path": "tests/test_text_utils.py", "content": "changed\n"},
                    ]
                },
            )
            assert result.is_error

    asyncio.run(check())
    assert allowed.read_bytes() == original_allowed
    assert protected.read_bytes() == original_protected


def test_read_rejects_junction_parent(workspace: Workspace) -> None:
    if os.name != "nt":
        pytest.skip("Windows directory junctions are unavailable")
    junction = workspace.root / "alias"
    try:
        creation = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(workspace.root / "tests")],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as error:
        pytest.skip(f"junction creation is unavailable: {error}")
    if creation.returncode != 0:
        pytest.skip(f"junction creation is unavailable: {creation.stderr.strip()}")
    assert junction.is_junction()

    async def check() -> None:
        async with Client(build_mcp_server(workspace), raise_exceptions=True) as client:
            result = await client.call_tool(
                "read_file", {"path": "alias/test_text_utils.py"}
            )
            assert result.is_error

    asyncio.run(check())


def test_read_rejects_symbolic_link_parent(workspace: Workspace) -> None:
    link = workspace.root / "alias"
    try:
        link.symlink_to(workspace.root / "tests", target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symbolic links are unavailable: {error}")

    async def check() -> None:
        async with Client(build_mcp_server(workspace), raise_exceptions=True) as client:
            result = await client.call_tool(
                "read_file", {"path": "alias/test_text_utils.py"}
            )
            assert result.is_error

    asyncio.run(check())


def test_read_alias_error_does_not_expose_host_path(workspace: Workspace) -> None:
    protected = workspace.root / "tests" / "test_text_utils.py"
    alias = workspace.root / "TESTS" / "test_text_utils.py"
    if not alias.exists() or not alias.samefile(protected):
        pytest.skip("workspace filesystem is case-sensitive")

    async def check() -> None:
        async with Client(build_mcp_server(workspace), raise_exceptions=True) as client:
            result = await client.call_tool(
                "read_file", {"path": "TESTS/test_text_utils.py"}
            )
            assert result.is_error
            error_text = " ".join(
                block.text for block in result.content if block.type == "text"
            )
            assert "filesystem path alias" in error_text
            assert str(workspace.root) not in error_text
            assert str(PROJECT_ROOT.parent) not in error_text

    asyncio.run(check())


def test_mutation_error_does_not_expose_host_path(workspace: Workspace) -> None:
    outside = workspace.root.parent / "outside.py"
    outside.write_bytes(b"original")
    linked = workspace.root / "linked.py"
    try:
        linked.hardlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"hard links are unavailable: {error}")

    async def check() -> None:
        async with Client(build_mcp_server(workspace), raise_exceptions=True) as client:
            result = await client.call_tool(
                "apply_file_changes",
                {"changes": [{"path": "linked.py", "content": "changed"}]},
            )
            assert result.is_error
            error_text = " ".join(
                block.text for block in result.content if block.type == "text"
            )
            assert "hard-linked target" in error_text
            assert str(workspace.root) not in error_text
            assert str(PROJECT_ROOT.parent) not in error_text

    asyncio.run(check())
    assert outside.read_bytes() == b"original"
    assert linked.read_bytes() == b"original"
