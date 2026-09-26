from dataclasses import replace
from pathlib import Path

import pytest

from coderepair.path_policy import is_path_writable, validate_workspace_path
from coderepair.tasks import TaskSpec, load_task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_001_MANIFEST = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001" / "task.yaml"


@pytest.fixture(scope="module")
def dev_task() -> TaskSpec:
    return load_task(DEV_001_MANIFEST)


def test_dev_001_implementation_is_writable(dev_task: TaskSpec) -> None:
    assert is_path_writable(dev_task, "text_utils.py")


@pytest.mark.parametrize(
    "path",
    ["tests/test_text_utils.py", "tests/unit/test_extra.py"],
)
def test_dev_001_tests_are_protected(dev_task: TaskSpec, path: str) -> None:
    assert not is_path_writable(dev_task, path)


def test_protected_pattern_takes_precedence(dev_task: TaskSpec) -> None:
    task = replace(
        dev_task,
        writable_paths=("src/**",),
        protected_paths=("src/generated/**",),
    )

    assert is_path_writable(task, "src/module.py")
    assert not is_path_writable(task, "src/generated/schema.py")


def test_path_matching_neither_policy_is_not_writable(dev_task: TaskSpec) -> None:
    assert not is_path_writable(dev_task, "README.md")
    assert not is_path_writable(dev_task, "package/module.py")


@pytest.mark.parametrize(
    "path",
    [
        "",
        "../outside.py",
        "src/../../outside.py",
        "/etc/passwd",
        "C:/outside.py",
        "C:\\outside.py",
        "C:outside.py",
    ],
)
def test_unsafe_paths_are_rejected(dev_task: TaskSpec, path: str) -> None:
    assert not is_path_writable(dev_task, path)
    with pytest.raises(ValueError):
        validate_workspace_path(path)
