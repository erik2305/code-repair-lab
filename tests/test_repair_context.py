import asyncio
from collections.abc import Iterator
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from mcp import Client

from coderepair.mcp_server import build_mcp_server
from coderepair.repair_context import (
    ContextFile,
    InitialRepairContext,
    build_initial_context,
    initial_context_sha256,
    render_initial_context,
)
from coderepair.tasks import load_task
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_001_DIRECTORY = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001"
DEV_001_MANIFEST = DEV_001_DIRECTORY / "task.yaml"
DEV_001_SNAPSHOT = DEV_001_DIRECTORY / "repo"


@pytest.fixture
def dev_workspace(tmp_path: Path) -> Iterator[Workspace]:
    workspace = create_workspace(DEV_001_MANIFEST, tmp_path / "workspace")
    yield workspace
    destroy_workspace(workspace)


def empty_workspace(tmp_path: Path) -> Workspace:
    root = tmp_path / "workspace"
    root.mkdir()
    return Workspace(task=load_task(DEV_001_MANIFEST), root=root.resolve())


def test_dev_001_context_includes_task_and_protected_test(
    dev_workspace: Workspace,
) -> None:
    source_file = DEV_001_SNAPSHOT / "text_utils.py"
    protected_test = DEV_001_SNAPSHOT / "tests" / "test_text_utils.py"
    source_before = source_file.read_bytes()
    test_before = protected_test.read_bytes()

    context = build_initial_context(
        dev_workspace, max_file_bytes=100_000, max_total_bytes=200_000
    )
    rendered = render_initial_context(context)

    assert context.task_id == "dev-001"
    assert context.bug_description == dev_workspace.task.bug_description
    assert context.writable_paths == ("*.py",)
    assert context.protected_paths == ("tests/**",)
    assert context.repository_paths == ("tests/test_text_utils.py", "text_utils.py")
    assert tuple(file.path for file in context.files) == context.repository_paths
    assert context.omitted_paths == ()
    assert context.withheld_paths == ()
    assert context.files[0].content == test_before.decode("utf-8")
    assert context.files[1].content == source_before.decode("utf-8")
    assert "FILE: tests/test_text_utils.py" in rendered
    assert "FILE: text_utils.py" in rendered
    assert source_file.read_bytes() == source_before
    assert protected_test.read_bytes() == test_before


def test_withheld_file_is_in_inventory_but_readable_later(
    dev_workspace: Workspace,
) -> None:
    withheld = Workspace(
        task=replace(dev_workspace.task, context_withheld_paths=("text_utils.py",)),
        root=dev_workspace.root,
    )
    context = build_initial_context(
        withheld, max_file_bytes=100_000, max_total_bytes=200_000
    )
    rendered = render_initial_context(context)
    assert "text_utils.py" in context.repository_paths
    assert "text_utils.py" in context.omitted_paths
    assert context.withheld_paths == ("text_utils.py",)
    assert 'value.strip(" ")' not in rendered
    assert "OMITTED FILE CONTENTS\n- text_utils.py" in rendered
    assert "CONTEXT-WITHHELD" not in rendered
    assert "intentionally withheld" not in rendered
    assert rendered.count("- text_utils.py") == 2  # inventory and neutral omission

    async def read() -> None:
        async with Client(
            build_mcp_server(withheld, image="unused", timeout_seconds=1),
            raise_exceptions=True,
        ) as client:
            result = await client.call_tool("read_file", {"path": "text_utils.py"})
            assert not result.is_error
            assert 'value.strip(" ")' in result.structured_content["result"]

    asyncio.run(read())


def test_withholding_reason_is_internal_only() -> None:
    neutral = InitialRepairContext(
        "task", "bug", ("*.py",), ("tests/**",), ("helper.py",), (),
        ("helper.py",),
    )
    intentionally_withheld = replace(neutral, withheld_paths=("helper.py",))

    assert render_initial_context(intentionally_withheld) == render_initial_context(
        neutral
    )
    assert initial_context_sha256(intentionally_withheld) == initial_context_sha256(
        neutral
    )
    assert intentionally_withheld.withheld_paths == ("helper.py",)


def test_missing_exact_withheld_file_fails_without_host_path(
    dev_workspace: Workspace,
) -> None:
    constrained = replace(
        dev_workspace,
        task=replace(
            dev_workspace.task, context_withheld_paths=("missing/helper.py",)
        ),
    )
    with pytest.raises(ValueError, match="missing/helper.py") as caught:
        build_initial_context(
            constrained, max_file_bytes=100_000, max_total_bytes=200_000
        )
    assert str(dev_workspace.root) not in str(caught.value)


def test_withheld_path_must_identify_an_ordinary_file(
    dev_workspace: Workspace,
) -> None:
    linked = dev_workspace.root / "linked.py"
    try:
        linked.symlink_to(dev_workspace.root / "text_utils.py")
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symbolic links are unavailable: {error}")
    constrained = replace(
        dev_workspace,
        task=replace(dev_workspace.task, context_withheld_paths=("linked.py",)),
    )
    with pytest.raises(ValueError, match="regular file") as caught:
        build_initial_context(
            constrained, max_file_bytes=100_000, max_total_bytes=200_000
        )
    assert str(dev_workspace.root) not in str(caught.value)


def test_withheld_directory_is_not_a_file(dev_workspace: Workspace) -> None:
    constrained = replace(
        dev_workspace,
        task=replace(dev_workspace.task, context_withheld_paths=("tests",)),
    )
    with pytest.raises(ValueError, match="existing regular files: tests"):
        build_initial_context(
            constrained, max_file_bytes=100_000, max_total_bytes=200_000
        )


def test_context_digest_uses_exact_default_rendering(dev_workspace: Workspace) -> None:
    context = build_initial_context(
        dev_workspace, max_file_bytes=100_000, max_total_bytes=200_000
    )
    rendered = render_initial_context(context)
    assert context.withheld_paths == ()
    assert "CONTEXT-WITHHELD" not in rendered
    assert (
        initial_context_sha256(context) == sha256(rendered.encode("utf-8")).hexdigest()
    )
    assert initial_context_sha256(context) == initial_context_sha256(
        build_initial_context(
            dev_workspace, max_file_bytes=100_000, max_total_bytes=200_000
        )
    )


def test_default_renderer_keeps_previous_byte_layout() -> None:
    context = InitialRepairContext(
        "task-1",
        "A bug.\n",
        ("*.py",),
        ("tests/**",),
        ("main.py", "tests/test_main.py"),
        (ContextFile("main.py", "x = 1\n"),),
        ("tests/test_main.py",),
    )
    expected = (
        "TASK\nid: task-1\n\n"
        "BUG DESCRIPTION\nA bug.\n\n"
        "WRITABLE PATHS\n- *.py\n\n"
        "PROTECTED PATHS\n- tests/**\n\n"
        "REPOSITORY FILES\n- main.py\n- tests/test_main.py\n\n"
        "FILE: main.py\n```python\nx = 1\n```\n\n"
        "OMITTED FILE CONTENTS\n- tests/test_main.py\n"
    )
    assert render_initial_context(context) == expected


def test_context_and_rendering_are_deterministic_and_pre_feedback(
    dev_workspace: Workspace,
) -> None:
    first = build_initial_context(
        dev_workspace, max_file_bytes=100_000, max_total_bytes=200_000
    )
    second = build_initial_context(
        dev_workspace, max_file_bytes=100_000, max_total_bytes=200_000
    )
    rendered = render_initial_context(first)

    assert first == second
    assert rendered == render_initial_context(second)
    assert first.repository_paths == tuple(sorted(first.repository_paths))
    assert tuple(file.path for file in first.files) == tuple(
        sorted(file.path for file in first.files)
    )
    assert str(dev_workspace.root) not in rendered
    assert str(dev_workspace.root.parent) not in rendered
    for command in (
        dev_workspace.task.reproduction_test,
        dev_workspace.task.full_test,
        dev_workspace.task.lint,
    ):
        assert repr(command) not in rendered


def test_per_file_limit_omits_complete_file(tmp_path: Path) -> None:
    workspace = empty_workspace(tmp_path)
    (workspace.root / "big.py").write_text("abcdefghij", encoding="utf-8")

    context = build_initial_context(workspace, max_file_bytes=5, max_total_bytes=100)

    assert context.repository_paths == ("big.py",)
    assert context.files == ()
    assert context.omitted_paths == ("big.py",)
    assert "abcdefghij" not in render_initial_context(context)


def test_total_limit_includes_whole_files_in_sorted_order(tmp_path: Path) -> None:
    workspace = empty_workspace(tmp_path)
    for name, content in (
        ("d.py", ""),
        ("c.py", "ccc"),
        ("b.py", "bb"),
        ("a.py", "aa"),
    ):
        (workspace.root / name).write_text(content, encoding="utf-8")

    context = build_initial_context(workspace, max_file_bytes=10, max_total_bytes=4)

    assert context.repository_paths == ("a.py", "b.py", "c.py", "d.py")
    assert tuple((file.path, file.content) for file in context.files) == (
        ("a.py", "aa"),
        ("b.py", "bb"),
    )
    assert context.omitted_paths == ("c.py", "d.py")


def test_invalid_utf8_is_listed_but_omitted(tmp_path: Path) -> None:
    workspace = empty_workspace(tmp_path)
    (workspace.root / "binary.dat").write_bytes(b"\xff\xfe")

    context = build_initial_context(workspace, max_file_bytes=10, max_total_bytes=10)

    assert context.repository_paths == ("binary.dat",)
    assert context.files == ()
    assert context.omitted_paths == ("binary.dat",)


def test_symbolic_link_is_not_followed(tmp_path: Path) -> None:
    workspace = empty_workspace(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text("outside secret", encoding="utf-8")
    link = workspace.root / "linked.py"
    try:
        link.symlink_to(outside)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symbolic links are unavailable: {error}")

    context = build_initial_context(workspace, max_file_bytes=100, max_total_bytes=100)

    assert context.repository_paths == ("linked.py",)
    assert context.files == ()
    assert context.omitted_paths == ("linked.py",)
    assert "outside secret" not in render_initial_context(context)


@pytest.mark.parametrize("invalid", [0, -1, True, 1.5, "10"])
@pytest.mark.parametrize("field", ["max_file_bytes", "max_total_bytes"])
def test_rejects_invalid_byte_limits(
    tmp_path: Path, field: str, invalid: object
) -> None:
    workspace = empty_workspace(tmp_path)
    limits = {"max_file_bytes": 10, "max_total_bytes": 10}
    limits[field] = invalid

    with pytest.raises(ValueError, match=field):
        build_initial_context(workspace, **limits)  # type: ignore[arg-type]
