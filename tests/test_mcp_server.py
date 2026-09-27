import asyncio
import os
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from mcp import Client
from mcp.server import MCPServer

import coderepair.docker_runner as docker_runner
import coderepair.evaluator as evaluator
import coderepair.mcp_server as mcp_server
from coderepair.docker_runner import CommandResult
from coderepair.mcp_server import build_mcp_server
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_001_DIRECTORY = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001"
DEV_001_MANIFEST = DEV_001_DIRECTORY / "task.yaml"
DEV_001_SNAPSHOT = DEV_001_DIRECTORY / "repo"
SANDBOX_IMAGE = "coderepair-lab-sandbox:dev"


def server_for(workspace: Workspace) -> MCPServer:
    return build_mcp_server(workspace, image=SANDBOX_IMAGE, timeout_seconds=30)


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Workspace]:
    result = create_workspace(DEV_001_MANIFEST, tmp_path / "workspace")
    yield result
    destroy_workspace(result)


def test_tools_and_readable_files(workspace: Workspace) -> None:
    server = server_for(workspace)
    assert isinstance(server, MCPServer)

    async def check() -> None:
        async with Client(server, raise_exceptions=True) as client:
            listed = await client.list_tools()
            assert {tool.name for tool in listed.tools} == {
                "read_file",
                "apply_file_changes",
                "run_reproduction",
                "run_full_tests",
                "run_lint",
            }
            schemas = {tool.name: tool.input_schema for tool in listed.tools}
            assert set(schemas["read_file"]["properties"]) == {"path"}
            assert set(schemas["apply_file_changes"]["properties"]) == {"changes"}
            for name in ("run_reproduction", "run_full_tests", "run_lint"):
                assert schemas[name]["properties"] == {}
                output_schema = next(
                    tool.output_schema for tool in listed.tools if tool.name == name
                )
                assert set(output_schema["properties"]) == {
                    "configured",
                    "exit_code",
                    "timed_out",
                    "duration_seconds",
                    "stdout",
                    "stderr",
                    "stdout_truncated",
                    "stderr_truncated",
                }

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
        async with Client(server_for(workspace), raise_exceptions=True) as client:
            result = await client.call_tool("read_file", {"path": path})
            assert result.is_error

    asyncio.run(check())


def test_read_rejects_missing_directory_binary_and_oversized_files(
    workspace: Workspace,
) -> None:
    (workspace.root / "invalid.py").write_bytes(b"\xff")
    (workspace.root / "large.py").write_bytes(b"x" * (256 * 1024 + 1))

    async def check() -> None:
        async with Client(server_for(workspace), raise_exceptions=True) as client:
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
        async with Client(server_for(workspace), raise_exceptions=True) as client:
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
        async with Client(server_for(workspace), raise_exceptions=True) as client:
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
        async with Client(server_for(workspace), raise_exceptions=True) as client:
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
        async with Client(server_for(workspace), raise_exceptions=True) as client:
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
        async with Client(server_for(workspace), raise_exceptions=True) as client:
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
        async with Client(server_for(workspace), raise_exceptions=True) as client:
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
        async with Client(server_for(workspace), raise_exceptions=True) as client:
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


def test_execution_tools_use_only_bound_commands(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[tuple[str, ...], str, float, bool]] = []

    def fake_run(
        bound_workspace: Workspace,
        argv: tuple[str, ...],
        *,
        image: str,
        timeout_seconds: float,
        workspace_read_only: bool,
    ) -> CommandResult:
        assert bound_workspace is workspace
        calls.append((tuple(argv), image, timeout_seconds, workspace_read_only))
        return CommandResult(tuple(argv), 1, "failed", "details", False, 0.25)

    monkeypatch.setattr(mcp_server, "run_in_docker", fake_run)

    async def check() -> None:
        async with Client(server_for(workspace), raise_exceptions=True) as client:
            for name in ("run_reproduction", "run_full_tests", "run_lint"):
                result = await client.call_tool(name, {})
                assert not result.is_error
                feedback = result.structured_content
                assert feedback["configured"] is True
                assert feedback["exit_code"] == 1
                assert feedback["timed_out"] is False
                assert feedback["duration_seconds"] == 0.25
                assert feedback["stdout"] == "failed"
                assert feedback["stderr"] == "details"
                assert feedback["stdout_truncated"] is False
                assert feedback["stderr_truncated"] is False

    asyncio.run(check())
    assert calls == [
        (command, SANDBOX_IMAGE, 30, True)
        for command in (
            workspace.task.reproduction_test,
            workspace.task.full_test,
            workspace.task.lint,
        )
    ]


def test_timeout_is_normal_execution_feedback(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timed_out_run(*args: object, **kwargs: object) -> CommandResult:
        return CommandResult(workspace.task.reproduction_test, None, "", "", True, 1.0)

    monkeypatch.setattr(mcp_server, "run_in_docker", timed_out_run)

    async def check() -> None:
        async with Client(server_for(workspace), raise_exceptions=True) as client:
            result = await client.call_tool("run_reproduction", {})
            assert not result.is_error
            feedback = result.structured_content
            assert feedback["exit_code"] is None
            assert feedback["timed_out"] is True

    asyncio.run(check())


def test_unconfigured_lint_does_not_run_docker(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_lint_workspace = replace(workspace, task=replace(workspace.task, lint=None))

    def unexpected_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("Docker must not run without a lint command")

    monkeypatch.setattr(mcp_server, "run_in_docker", unexpected_run)

    async def check() -> None:
        async with Client(
            server_for(no_lint_workspace), raise_exceptions=True
        ) as client:
            result = await client.call_tool("run_lint", {})
            assert not result.is_error
            feedback = result.structured_content
            assert feedback == {
                "configured": False,
                "exit_code": None,
                "timed_out": False,
                "duration_seconds": None,
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
            }

    asyncio.run(check())


def test_execution_output_is_bounded_and_hides_host_path(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    large_output = "BEGIN" + "x" * 40000 + str(workspace.root) + "TAIL"

    def fake_run(*args: object, **kwargs: object) -> CommandResult:
        return CommandResult(
            workspace.task.reproduction_test,
            0,
            large_output,
            large_output.replace("BEGIN", "ERROR"),
            False,
            0.1,
        )

    monkeypatch.setattr(mcp_server, "run_in_docker", fake_run)

    async def check() -> None:
        async with Client(server_for(workspace), raise_exceptions=True) as client:
            result = await client.call_tool("run_reproduction", {})
            assert not result.is_error
            feedback = result.structured_content
            for key, beginning in (("stdout", "BEGIN"), ("stderr", "ERROR")):
                stream = feedback[key]
                assert len(stream.encode("utf-8")) <= 32 * 1024
                assert stream.startswith(beginning)
                assert stream.endswith("TAIL")
                assert "[output truncated]" in stream
                assert str(workspace.root) not in stream
                assert feedback[f"{key}_truncated"] is True

    asyncio.run(check())


def test_execution_infrastructure_failure_is_sanitized_tool_error(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable_run(*args: object, **kwargs: object) -> CommandResult:
        raise OSError(f"Docker failed near {workspace.root}")

    monkeypatch.setattr(mcp_server, "run_in_docker", unavailable_run)

    async def check() -> None:
        async with Client(server_for(workspace), raise_exceptions=True) as client:
            result = await client.call_tool("run_reproduction", {})
            assert result.is_error
            error_text = " ".join(
                block.text for block in result.content if block.type == "text"
            )
            assert "Docker execution failed" in error_text
            assert str(workspace.root) not in error_text
            assert str(PROJECT_ROOT.parent) not in error_text

    asyncio.run(check())


@pytest.fixture(scope="module")
def docker_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    try:
        daemon = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"Docker daemon is unavailable: {error}")
    if daemon.returncode != 0:
        pytest.skip("Docker daemon is unavailable")

    image = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if image.returncode != 0:
        pytest.skip(f"sandbox image is unavailable: {SANDBOX_IMAGE}")
    return SANDBOX_IMAGE


def test_mcp_feedback_cycle_repairs_dev_001(
    workspace: Workspace, docker_image: str
) -> None:
    async def check() -> None:
        async with Client(server_for(workspace), raise_exceptions=True) as client:
            read = await client.call_tool("read_file", {"path": "text_utils.py"})
            assert not read.is_error
            assert 'value.strip(" ")' in read.structured_content["result"]

            for name, expected_exit in (
                ("run_reproduction", 1),
                ("run_full_tests", 1),
                ("run_lint", 0),
            ):
                result = await client.call_tool(name, {})
                assert not result.is_error
                assert result.structured_content["configured"] is True
                assert result.structured_content["exit_code"] == expected_exit
                assert result.structured_content["timed_out"] is False

            mutation = await client.call_tool(
                "apply_file_changes",
                {
                    "changes": [
                        {
                            "path": "text_utils.py",
                            "content": (
                                '"""Small text normalization helpers."""\n\n\n'
                                "def normalize_name(value: str) -> str:\n"
                                '    """Remove surrounding whitespace from a name."""\n'
                                "    return value.strip()\n"
                            ),
                        }
                    ]
                },
            )
            assert not mutation.is_error

            for name in ("run_reproduction", "run_full_tests", "run_lint"):
                result = await client.call_tool(name, {})
                assert not result.is_error
                assert result.structured_content["configured"] is True
                assert result.structured_content["exit_code"] == 0
                assert result.structured_content["timed_out"] is False

    asyncio.run(check())


def test_mcp_feedback_cannot_modify_protected_test(
    workspace: Workspace, docker_image: str
) -> None:
    protected = workspace.root / "tests" / "test_text_utils.py"
    original = protected.read_bytes()

    async def check() -> None:
        async with Client(server_for(workspace), raise_exceptions=True) as client:
            mutation = await client.call_tool(
                "apply_file_changes",
                {
                    "changes": [
                        {
                            "path": "text_utils.py",
                            "content": (
                                "from pathlib import Path\n"
                                "Path('tests/test_text_utils.py').write_text("
                                "'def test_cheat(): pass\\n')\n"
                                "def normalize_name(value: str) -> str:\n"
                                "    return value.strip()\n"
                            ),
                        }
                    ]
                },
            )
            assert not mutation.is_error
            result = await client.call_tool("run_reproduction", {})
            assert not result.is_error
            assert result.structured_content["exit_code"] != 0
            assert result.structured_content["timed_out"] is False

    asyncio.run(check())
    assert protected.read_bytes() == original
