"""Preregistered DEV-v2 states; reference edits stay outside snapshots."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from coderepair.docker_runner import CommandResult, run_in_docker
from coderepair.evaluator import evaluate_workspace
from coderepair.file_changes import FileChange, apply_file_changes
from coderepair.repair_context import build_initial_context
from coderepair.tasks import SnapshotSource, load_task
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

BENCHMARK_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "dev"
SANDBOX_IMAGE = "coderepair-lab-sandbox:dev"
Edit = tuple[str, str, str]

_PARTIAL_SPLITTER = r"""def split_fields(text: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == ";":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields"""

_COMPLETE_SPLITTER = r"""def split_fields(text: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    quoted = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == '"':
            current.append(char)
            quoted = not quoted
        elif char == ";" and not quoted:
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    fields.append("".join(current))
    return fields"""


@dataclass(frozen=True)
class Case:
    task_id: str
    reproduction_node: str
    regression_node: str
    writable: tuple[str, ...]
    partial: tuple[Edit, ...]
    canonical: tuple[Edit, ...]


CASES = (
    Case(
        "dev-005",
        "tests/test_service.py::test_update_refreshes_summary",
        "tests/test_service.py::test_repeated_read_reuses_cached_summary",
        ("store.py", "cache.py", "service.py"),
        (
            (
                "service.py",
                'return self.cache.get(key, lambda: f"{key}: {self.store.get(key)}")',
                'return f"{key}: {self.store.get(key)}"',
            ),
        ),
        (
            (
                "service.py",
                "self.store.update(key, value)",
                "self.store.update(key, value)\n        self.cache.invalidate(key)",
            ),
        ),
    ),
    Case(
        "dev-006",
        "tests/test_loader.py::test_invalid_numeric_value_uses_public_error",
        "tests/test_loader.py::test_internal_failure_is_not_relabelled",
        ("parser.py", "loader.py", "errors.py"),
        (
            (
                "loader.py",
                "from errors import ConfigError, EntrySyntaxError",
                "from errors import ConfigError",
            ),
            (
                "loader.py",
                "except EntrySyntaxError as error:",
                "except Exception as error:",
            ),
        ),
        (
            (
                "loader.py",
                "from errors import ConfigError, EntrySyntaxError",
                "from errors import ConfigError, EntrySyntaxError, NumericValueError",
            ),
            (
                "loader.py",
                "except EntrySyntaxError as error:",
                "except (EntrySyntaxError, NumericValueError) as error:",
            ),
        ),
    ),
    Case(
        "dev-007",
        "tests/test_storage.py::test_current_record_roundtrip",
        "tests/test_storage.py::test_legacy_record_remains_readable",
        ("schema.py", "codec.py", "storage.py"),
        (
            (
                "codec.py",
                'return Record(name=data["name"], age=data["age"])',
                'return Record(name=data["payload"]["name"], '
                'age=data["payload"]["age"])',
            ),
        ),
        (
            (
                "codec.py",
                'return Record(name=data["name"], age=data["age"])',
                'payload = data["payload"] if data.get("version") == 2 else data\n'
                '    return Record(name=payload["name"], age=payload["age"])',
            ),
        ),
    ),
    Case(
        "dev-008",
        "tests/test_service.py::test_rejected_order_keeps_stock",
        "tests/test_service.py::test_rejected_order_keeps_ledger_empty",
        ("inventory.py", "ledger.py", "service.py", "validators.py"),
        (
            (
                "service.py",
                "self.inventory.take(item, quantity)\n"
                "        self.ledger.record(item, quantity)\n"
                "        validate_customer(customer)",
                "self.ledger.record(item, quantity)\n"
                "        validate_customer(customer)\n"
                "        self.inventory.take(item, quantity)",
            ),
        ),
        (
            (
                "service.py",
                "self.inventory.take(item, quantity)\n"
                "        self.ledger.record(item, quantity)\n"
                "        validate_customer(customer)",
                "validate_customer(customer)\n"
                "        self.inventory.take(item, quantity)\n"
                "        self.ledger.record(item, quantity)",
            ),
        ),
    ),
    Case(
        "dev-009",
        "tests/test_resolver.py::test_nested_manifest_resolves_its_own_data",
        "tests/test_resolver.py::test_deeper_include_uses_its_declaring_manifest",
        ("manifest.py", "paths.py", "resolver.py"),
        (
            (
                "resolver.py",
                "data.append(resolve_reference(base, reference))",
                "data.append(resolve_reference(manifest, reference))",
            ),
        ),
        (
            (
                "resolver.py",
                "def visit(manifest: str, base: str) -> None:",
                "def visit(manifest: str) -> None:",
            ),
            (
                "resolver.py",
                "child = resolve_reference(base, reference)",
                "child = resolve_reference(manifest, reference)",
            ),
            ("resolver.py", "visit(child, base)", "visit(child)"),
            (
                "resolver.py",
                "data.append(resolve_reference(base, reference))",
                "data.append(resolve_reference(manifest, reference))",
            ),
            ("resolver.py", "visit(root, root)", "visit(root)"),
        ),
    ),
    Case(
        "dev-010",
        "tests/test_query.py::test_escaped_separator_stays_inside_value",
        "tests/test_query.py::test_quoted_separator_stays_inside_value",
        ("tokenizer.py", "normalizer.py", "query.py"),
        (
            (
                "tokenizer.py",
                'def split_fields(text: str) -> list[str]:\n    return text.split(";")',
                _PARTIAL_SPLITTER,
            ),
        ),
        (
            (
                "tokenizer.py",
                'def split_fields(text: str) -> list[str]:\n    return text.split(";")',
                _COMPLETE_SPLITTER,
            ),
        ),
    ),
)


def _manifest(case: Case) -> Path:
    return BENCHMARK_ROOT / case.task_id / "task.yaml"


def _snapshot_files(case: Case) -> dict[str, bytes]:
    root = BENCHMARK_ROOT / case.task_id / "repo"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _apply_edits(workspace: Workspace, edits: tuple[Edit, ...]) -> None:
    contents: dict[str, str] = {}
    for relative, old, new in edits:
        source = contents.get(relative)
        if source is None:
            source = (workspace.root / relative).read_text(encoding="utf-8")
        assert source.count(old) == 1, (relative, old)
        contents[relative] = source.replace(old, new)
    apply_file_changes(
        workspace,
        [FileChange(path, content) for path, content in contents.items()],
    )


def _run_checks(workspace: Workspace, image: str) -> tuple[CommandResult, ...]:
    commands = (
        workspace.task.reproduction_test,
        workspace.task.full_test,
        workspace.task.lint,
    )
    return tuple(
        run_in_docker(
            workspace,
            command,
            image=image,
            timeout_seconds=30,
            workspace_read_only=True,
        )
        for command in commands
    )


@pytest.fixture(scope="module")
def docker_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    try:
        daemon = subprocess.run(
            ["docker", "info"], capture_output=True, check=False, text=True, timeout=10
        )
        if daemon.returncode != 0:
            pytest.skip("Docker daemon is unavailable")
        image = subprocess.run(
            ["docker", "image", "inspect", SANDBOX_IMAGE],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"Docker is unavailable: {error}")
    if image.returncode != 0:
        pytest.skip(f"sandbox image is unavailable: {SANDBOX_IMAGE}")
    return SANDBOX_IMAGE


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.task_id)
def test_manifest_and_complete_initial_context(tmp_path: Path, case: Case) -> None:
    task = load_task(_manifest(case))
    assert task.id == case.task_id
    assert task.source == SnapshotSource(type="snapshot", path="repo")
    assert task.reproduction_test == ("python", "-m", "pytest", case.reproduction_node)
    assert task.full_test == ("python", "-m", "pytest")
    assert task.lint == ("ruff", "check", "--ignore", "EXE002", ".")
    assert task.writable_paths == case.writable
    assert task.protected_paths == ("tests/**",)

    before = _snapshot_files(case)
    workspace = create_workspace(_manifest(case), tmp_path / "workspace")
    try:
        context = build_initial_context(
            workspace, max_file_bytes=100_000, max_total_bytes=200_000
        )
        assert context.omitted_paths == ()
        assert context.repository_paths == tuple(sorted(before))
        assert tuple(file.path for file in context.files) == context.repository_paths
    finally:
        destroy_workspace(workspace)
    assert _snapshot_files(case) == before


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.task_id)
def test_original_state(tmp_path: Path, docker_image: str, case: Case) -> None:
    before = _snapshot_files(case)
    workspace = create_workspace(_manifest(case), tmp_path / "workspace")
    try:
        reproduction, full_test, lint = _run_checks(workspace, docker_image)
        assert reproduction.exit_code == 1, reproduction.stdout
        assert full_test.exit_code == 1, full_test.stdout
        assert lint.exit_code == 0, lint.stdout + lint.stderr
        assert not any(result.timed_out for result in (reproduction, full_test, lint))
    finally:
        destroy_workspace(workspace)
    assert _snapshot_files(case) == before


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.task_id)
def test_partial_repair_passes_reproduction_but_fails_regression(
    tmp_path: Path, docker_image: str, case: Case
) -> None:
    before = _snapshot_files(case)
    workspace = create_workspace(_manifest(case), tmp_path / "workspace")
    try:
        _apply_edits(workspace, case.partial)
        reproduction, full_test, lint = _run_checks(workspace, docker_image)
        assert reproduction.exit_code == 0, reproduction.stdout + reproduction.stderr
        assert full_test.exit_code == 1, full_test.stdout
        assert case.regression_node in full_test.stdout
        assert "1 failed" in full_test.stdout
        assert lint.exit_code == 0, lint.stdout + lint.stderr
        assert not any(result.timed_out for result in (reproduction, full_test, lint))
    finally:
        destroy_workspace(workspace)
    assert _snapshot_files(case) == before


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.task_id)
def test_canonical_repair_passes_independent_evaluator(
    tmp_path: Path, docker_image: str, case: Case
) -> None:
    before = _snapshot_files(case)
    workspace = create_workspace(_manifest(case), tmp_path / "workspace")
    try:
        _apply_edits(workspace, case.canonical)
        result = evaluate_workspace(
            _manifest(case), workspace, image=docker_image, timeout_seconds=30
        )
        assert result.success, result
        assert result.writable_paths_respected
        assert result.unauthorized_changes == ()
        assert result.protected_paths_unchanged
        assert result.protected_changes == ()
        assert result.reproduction is not None
        assert result.reproduction.exit_code == 0
        assert result.full_test is not None
        assert result.full_test.exit_code == 0
        assert result.lint is not None
        assert result.lint.exit_code == 0
        assert not any(
            command.timed_out
            for command in (result.reproduction, result.full_test, result.lint)
        )
    finally:
        destroy_workspace(workspace)
    assert _snapshot_files(case) == before
