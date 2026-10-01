"""Trusted, deterministic validation of the frozen DEV-v3 fixture roles."""

import asyncio
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from mcp import Client

from coderepair.docker_runner import CommandResult, run_in_docker
from coderepair.evaluator import evaluate_workspace
from coderepair.file_changes import FileChange, apply_file_changes
from coderepair.mcp_server import build_mcp_server
from coderepair.repair_context import build_initial_context, render_initial_context
from coderepair.tasks import SnapshotSource, load_task
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

BENCHMARK_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "dev"
SANDBOX_IMAGE = "coderepair-lab-sandbox:dev"
TASK_IDS = tuple(f"dev-{number:03}" for number in range(11, 17))
WITHHELD = {
    "dev-011": ("display_time.py", "fixtures/poll_case.json", "poll_hint.py"),
    "dev-012": ("cursor_codec.py", "page_limits.py"),
    "dev-013": ("fixtures/sample.packet",),
    "dev-014": ("fixtures/sample.packet",),
    "dev-015": ("tests/test_policy_integration.py",),
    "dev-016": ("fixtures/index.json", "tests/test_resolver_integration.py"),
}
WRITABLE = {
    "dev-011": ("scheduler.py",),
    "dev-012": ("window.py",),
    "dev-013": ("loader.py",),
    "dev-014": ("normalize.py",),
    "dev-015": ("authorizer.py", "policy.py"),
    "dev-016": ("constraints.py", "resolver.py"),
}

# Trusted reference edits are deliberately outside the model-visible snapshots.
REPAIRS = {
    "dev-011": (
        (
            "scheduler.py",
            "from poll_hint import parse_poll_hint",
            "from poll_hint import SLOTS_PER_SECOND, parse_poll_hint",
        ),
        (
            "scheduler.py",
            "return now + delay",
            "return now + delay / SLOTS_PER_SECOND",
        ),
    ),
    "dev-012": (
        (
            "window.py",
            "end = min(len(items) - 1, offset + count)",
            "end = min(len(items), offset + count)",
        ),
    ),
    "dev-013": (
        (
            "loader.py",
            "return parse_binary(payload)",
            'return parse_binary(payload.rstrip(b"\\r\\n"))',
        ),
    ),
    "dev-014": (
        ("normalize.py", "if value}", "if value is not None}"),
    ),
    "dev-015": (
        (
            "authorizer.py",
            "checked_group = require_group(group)\n"
            "    canonical_group = expand_alias(checked_group)",
            "canonical_group = require_group(expand_alias(group))",
        ),
        (
            "policy.py",
            "    for rule in rules:\n"
            '        if rule.group == group and rule.resource in (resource, "*"):\n'
            '            return rule.effect == "allow"\n'
            "    return False",
            "    matching = [\n"
            "        rule for rule in rules\n"
            '        if rule.group == group and rule.resource in (resource, "*")\n'
            "    ]\n"
            '    if any(rule.effect == "deny" for rule in matching):\n'
            "        return False\n"
            '    return any(rule.effect == "allow" for rule in matching)',
        ),
    ),
    "dev-016": (
        (
            "constraints.py",
            "return version_key(release) > version_key(minimum)",
            "return version_key(release) >= version_key(minimum)",
        ),
        (
            "resolver.py",
            "from constraints import accepts",
            "from constraints import accepts\nfrom versions import version_key",
        ),
        (
            "resolver.py",
            "return max(candidates)",
            "return max(candidates, key=version_key)",
        ),
    ),
}
F2_MESSAGES = {
    "dev-015": "explicit deny must override allow",
    "dev-016": "latest allowed version must use numeric ordering",
}


def _manifest(task_id: str) -> Path:
    return BENCHMARK_ROOT / task_id / "task.yaml"


def _snapshot_files(task_id: str) -> dict[str, bytes]:
    root = BENCHMARK_ROOT / task_id / "repo"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _apply_repair(workspace: Workspace, task_id: str, *, partial: bool = False) -> None:
    edits = REPAIRS[task_id][:1] if partial else REPAIRS[task_id]
    content_by_path: dict[str, str] = {}
    for path, old, new in edits:
        source = content_by_path.get(path)
        if source is None:
            source = (workspace.root / path).read_text(encoding="utf-8")
        assert source.count(old) == 1, (task_id, path, old)
        content_by_path[path] = source.replace(old, new)
    apply_file_changes(
        workspace,
        tuple(FileChange(path, content) for path, content in content_by_path.items()),
    )


def _run_checks(workspace: Workspace, image: str) -> tuple[CommandResult, ...]:
    return tuple(
        run_in_docker(
            workspace,
            command,
            image=image,
            timeout_seconds=30,
            workspace_read_only=True,
        )
        for command in (
            workspace.task.reproduction_test,
            workspace.task.full_test,
            workspace.task.lint,
        )
    )


async def _mcp_tool(workspace: Workspace, name: str, arguments: dict) -> dict:
    server = build_mcp_server(workspace, image=SANDBOX_IMAGE, timeout_seconds=30)
    async with Client(server, raise_exceptions=True) as client:
        result = await client.call_tool(name, arguments)
        assert not result.is_error
        assert result.structured_content is not None
        return result.structured_content


@pytest.fixture(scope="module")
def docker_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    try:
        daemon = subprocess.run(
            ["docker", "info"], capture_output=True, check=False, text=True, timeout=10
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


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_manifest_inventory_and_withholding(task_id: str, tmp_path: Path) -> None:
    task = load_task(_manifest(task_id))
    assert task.id == task_id
    assert task.source == SnapshotSource(type="snapshot", path="repo")
    assert task.reproduction_test[:3] == ("python", "-m", "pytest")
    assert task.full_test == ("python", "-m", "pytest")
    assert task.lint == ("ruff", "check", "--ignore", "EXE002", ".")
    assert task.writable_paths == WRITABLE[task_id]
    assert task.protected_paths == ("tests/**",)
    assert task.context_withheld_paths == WITHHELD[task_id]

    workspace = create_workspace(_manifest(task_id), tmp_path / "workspace")
    try:
        context = build_initial_context(
            workspace, max_file_bytes=100_000, max_total_bytes=200_000
        )
        rendered = render_initial_context(context)
        assert context.repository_paths == tuple(sorted(_snapshot_files(task_id)))
        assert context.withheld_paths == WITHHELD[task_id]
        assert "CONTEXT-WITHHELD" not in rendered
        assert "intentionally withheld" not in rendered
        application_files = [
            path
            for path in context.repository_paths
            if path.endswith(".py") and not path.startswith("tests/")
        ]
        assert len(application_files) >= 2
        for path in WITHHELD[task_id]:
            assert path in context.repository_paths
            assert path in context.omitted_paths
            assert f"FILE: {path}\n" not in rendered
            assert (workspace.root / path).is_file()
        if task_id in {"dev-011", "dev-012", "dev-013", "dev-014"}:
            for path in WITHHELD[task_id]:
                read = asyncio.run(_mcp_tool(workspace, "read_file", {"path": path}))
                assert read["result"] == (workspace.root / path).read_text(
                    encoding="utf-8"
                )
    finally:
        destroy_workspace(workspace)


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_original_snapshot_fails_and_lints(
    task_id: str, tmp_path: Path, docker_image: str
) -> None:
    original = _snapshot_files(task_id)
    workspace = create_workspace(_manifest(task_id), tmp_path / "workspace")
    try:
        reproduction, full_test, lint = _run_checks(workspace, docker_image)
        assert reproduction.exit_code == 1, reproduction.stdout
        assert full_test.exit_code == 1, full_test.stdout
        assert lint.exit_code == 0, lint.stdout + lint.stderr
        assert not any(result.timed_out for result in (reproduction, full_test, lint))
    finally:
        destroy_workspace(workspace)
    assert _snapshot_files(task_id) == original


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_canonical_repair_passes_independent_evaluator(
    task_id: str, tmp_path: Path, docker_image: str
) -> None:
    original = _snapshot_files(task_id)
    workspace = create_workspace(_manifest(task_id), tmp_path / "workspace")
    try:
        _apply_repair(workspace, task_id)
        for path in WITHHELD[task_id]:
            assert (workspace.root / path).read_bytes() == original[path]
        result = evaluate_workspace(
            _manifest(task_id), workspace, image=docker_image, timeout_seconds=30
        )
        assert result.success, (
            result.reproduction.stdout if result.reproduction else None,
            result.full_test.stdout if result.full_test else None,
            result.lint.stdout if result.lint else None,
        )
        assert result.writable_paths_respected
        assert result.protected_paths_unchanged
        assert result.unauthorized_changes == ()
        assert result.protected_changes == ()
        assert result.reproduction is not None and result.reproduction.exit_code == 0
        assert result.full_test is not None and result.full_test.exit_code == 0
        assert result.lint is not None and result.lint.exit_code == 0
    finally:
        destroy_workspace(workspace)
    assert _snapshot_files(task_id) == original


def test_dev011_hidden_parser_defines_unit_contract(tmp_path: Path) -> None:
    workspace = create_workspace(_manifest("dev-011"), tmp_path / "workspace")
    try:
        context = build_initial_context(
            workspace, max_file_bytes=100_000, max_total_bytes=200_000
        )
        rendered = render_initial_context(context)
        critical_fact = "quarter-second scheduling slots"
        assert context.withheld_paths == WITHHELD["dev-011"]
        assert critical_fact not in workspace.task.bug_description
        assert critical_fact not in rendered
        assert "SLOTS_PER_SECOND" not in rendered
        assert "slot:18" not in rendered
        assert "1004.5" not in rendered
        for path in context.repository_paths:
            if path not in context.withheld_paths:
                assert critical_fact not in (workspace.root / path).read_text(
                    encoding="utf-8"
                )
        helper = asyncio.run(
            _mcp_tool(workspace, "read_file", {"path": "poll_hint.py"})
        )["result"]
        distractor = asyncio.run(
            _mcp_tool(workspace, "read_file", {"path": "display_time.py"})
        )["result"]
        assert critical_fact in helper
        assert "SLOTS_PER_SECOND = 4" in helper
        assert critical_fact not in distractor
    finally:
        destroy_workspace(workspace)


def test_dev013_runtime_backend_discriminator_is_observed(
    tmp_path: Path, docker_image: str
) -> None:
    workspace = create_workspace(_manifest("dev-013"), tmp_path / "workspace")
    try:
        context = render_initial_context(
            build_initial_context(
                workspace, max_file_bytes=100_000, max_total_bytes=200_000
            )
        )
        feedback = asyncio.run(_mcp_tool(workspace, "run_reproduction", {}))
        observation = json.dumps(feedback, sort_keys=True, ensure_ascii=False)
        # H1: a BOM-prefixed text packet is sniffed as text, but its strict
        # backend could reject the unnormalized header. H2: a line-terminated
        # binary packet is sniffed as binary, but strict framing could reject
        # the extra transport bytes. Both normal backend paths are valid.
        sniffer = (workspace.root / "sniffer.py").read_text(encoding="utf-8")
        loader = (workspace.root / "loader.py").read_text(encoding="utf-8")
        text_backend = (workspace.root / "text_backend.py").read_text(
            encoding="utf-8"
        )
        binary_backend = (workspace.root / "binary_backend.py").read_text(
            encoding="utf-8"
        )
        assert "removeprefix" in sniffer
        assert "return parse_text(payload)" in loader
        assert "return parse_binary(payload)" in loader
        assert 'packet.startswith(b"TX|")' in text_backend
        assert "len(body) != length" in binary_backend
        assert feedback["exit_code"] == 1
        assert not feedback["timed_out"]
        assert "BX|1:7" not in context
        assert "binary_backend.py:" not in context
        assert re.search(r"binary_backend\.py:\d+", observation)
        discriminator = "binary packet length mismatch: expected 1, received 2"
        assert discriminator in observation
        assert discriminator not in context
    finally:
        destroy_workspace(workspace)


def test_dev014_backend_diagnostic_is_not_needed_for_common_repair(
    tmp_path: Path, docker_image: str
) -> None:
    workspace = create_workspace(_manifest("dev-014"), tmp_path / "workspace")
    try:
        feedback = asyncio.run(_mcp_tool(workspace, "run_reproduction", {}))
        assert feedback["exit_code"] == 1
        assert "binary_backend.py:" in feedback["stdout"]
        assert "normalize.py:" in feedback["stdout"]
        source = (workspace.root / "normalize.py").read_text(encoding="utf-8")
        assert "if value}" in source
        assert b"TX|retry_count=0" in (
            workspace.root / "tests/test_loader.py"
        ).read_bytes()
    finally:
        destroy_workspace(workspace)


@pytest.mark.parametrize("task_id", ("dev-015", "dev-016"))
def test_progressive_f1_then_f2_after_trusted_partial(
    task_id: str, tmp_path: Path, docker_image: str
) -> None:
    original = _snapshot_files(task_id)
    workspace = create_workspace(_manifest(task_id), tmp_path / "workspace")
    try:
        context = render_initial_context(
            build_initial_context(
                workspace, max_file_bytes=100_000, max_total_bytes=200_000
            )
        )
        original_repro, original_full, original_lint = _run_checks(
            workspace, docker_image
        )
        assert (
            original_repro.exit_code,
            original_full.exit_code,
            original_lint.exit_code,
        ) == (1, 1, 0)
        assert F2_MESSAGES[task_id] not in context
        assert F2_MESSAGES[task_id] not in original_repro.stdout
        assert F2_MESSAGES[task_id] not in original_full.stdout
        f1 = "UnknownGroupError" if task_id == "dev-015" else "NoCandidateError"
        assert f1 in original_repro.stdout
        assert f1 in original_full.stdout

        _apply_repair(workspace, task_id, partial=True)
        partial_repro, partial_full, partial_lint = _run_checks(workspace, docker_image)
        assert (
            partial_repro.exit_code,
            partial_full.exit_code,
            partial_lint.exit_code,
        ) == (0, 1, 0)
        assert f1 not in partial_repro.stdout
        assert F2_MESSAGES[task_id] in partial_full.stdout
        partial_evaluation = evaluate_workspace(
            _manifest(task_id), workspace, image=docker_image, timeout_seconds=30
        )
        assert not partial_evaluation.success
        assert partial_evaluation.writable_paths_respected
        assert partial_evaluation.protected_paths_unchanged
    finally:
        destroy_workspace(workspace)
    assert _snapshot_files(task_id) == original
