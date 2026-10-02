"""Inherited-permission scratch lifecycle and real mounted DEV-v3 preflight."""

import os
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_docker_runner import docker_image  # noqa: F401 -- shared Docker fixture

import coderepair.agent_evidence as evidence
from coderepair.agent_evidence import shadow_evaluate_batches
from coderepair.baseline import render_single_shot_prompt
from coderepair.dev_v3_experiment import workspace_context
from coderepair.experiment import pin_docker_image
from coderepair.experiment_workspace import temporary_experiment_workspace
from coderepair.file_changes import FileChange
from coderepair.repair_context import initial_context_sha256
from coderepair.run_config import RunConfig
from coderepair.workspace import create_workspace
from scripts import run_dev_v3_experiment as runner

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks/dev/dev-013/task.yaml"
CONFIG = RunConfig("fake", "medium", 4096, 60, 30, 100000, 200000, "sandbox:dev")


def test_unique_fresh_children_cleanup_and_location_neutral_context(tmp_path):
    source = MANIFEST.parent / "repo/loader.py"
    original = source.read_bytes()
    scratch = tmp_path / ".coderepair-tmp"
    children, contexts = [], []
    for _ in range(2):
        with temporary_experiment_workspace(scratch) as child:
            assert child.parent == scratch.resolve()
            assert not list(child.iterdir())
            children.append(child)
            workspace = create_workspace(MANIFEST, child / "workspace")
            contexts.append(workspace_context(workspace, CONFIG))
            (workspace.root / "loader.py").write_text("changed", encoding="utf-8")
        assert not child.exists()
    assert children[0] != children[1]
    assert scratch.is_dir()
    assert source.read_bytes() == original
    assert contexts[0] == contexts[1]
    assert initial_context_sha256(contexts[0]) == initial_context_sha256(contexts[1])
    assert render_single_shot_prompt(contexts[0]) == render_single_shot_prompt(
        contexts[1]
    )


def test_cleanup_when_workspace_creation_or_body_fails(tmp_path):
    scratch = tmp_path / "scratch"
    with pytest.raises(FileNotFoundError):
        with temporary_experiment_workspace(scratch) as child:
            create_workspace(tmp_path / "missing.yaml", child / "workspace")
    assert not list(scratch.iterdir())
    with pytest.raises(RuntimeError, match="body failed"):
        with temporary_experiment_workspace(scratch) as child:
            create_workspace(MANIFEST, child / "workspace")
            raise RuntimeError("body failed")
    assert not list(scratch.iterdir())


def test_ordinary_mkdir_does_not_request_private_temp_mode(tmp_path, monkeypatch):
    actual = Path.mkdir
    modes = []

    def mkdir(path, mode=0o777, **kwargs):
        modes.append(mode)
        return actual(path, mode=mode, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    with temporary_experiment_workspace(tmp_path / "scratch"):
        pass
    assert modes == [0o777, 0o777]


def test_file_scratch_parent_rejected(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.write_text("not a directory")
    with pytest.raises(NotADirectoryError):
        with temporary_experiment_workspace(scratch):
            pytest.fail("must not enter")


@pytest.mark.parametrize("ancestor", [False, True])
def test_symlink_scratch_parent_or_ancestor_rejected(tmp_path, ancestor):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    scratch = link / "scratch" if ancestor else link
    with pytest.raises(ValueError, match="links"):
        with temporary_experiment_workspace(scratch):
            pytest.fail("must not follow link")
    assert not list(target.iterdir())


@pytest.mark.parametrize("ancestor", [False, True])
def test_junction_scratch_parent_or_ancestor_rejected(tmp_path, ancestor):
    if os.name != "nt":
        pytest.skip("Windows directory junctions are unavailable")
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "junction"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("junction creation unavailable")
    try:
        scratch = link / "scratch" if ancestor else link
        with pytest.raises(ValueError, match="links"):
            with temporary_experiment_workspace(scratch):
                pytest.fail("must not follow junction")
        assert not list(target.iterdir())
    finally:
        link.rmdir()


def test_scratch_root_is_git_ignored():
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            ".coderepair-tmp/workspace-example/workspace/loader.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.parametrize("explicit_root", [False, True])
def test_shadow_optional_scratch_and_legacy_default(
    tmp_path, monkeypatch, explicit_root
):
    roots = []
    actual_create = evidence.create_workspace
    scratch = tmp_path / "scratch"

    def create(manifest, destination):
        roots.append(destination)
        return actual_create(manifest, destination)

    def evaluate(*args, **kwargs):
        raise RuntimeError("stop before Docker")

    monkeypatch.setattr(evidence, "create_workspace", create)
    monkeypatch.setattr(evidence, "evaluate_workspace", evaluate)
    with pytest.raises(RuntimeError, match="stop before Docker"):
        shadow_evaluate_batches(
            MANIFEST,
            ((FileChange("loader.py", "changed"),),),
            image="unused",
            timeout_seconds=30,
            **({"scratch_root": scratch} if explicit_root else {}),
        )
    assert len(roots) == 1
    assert not roots[0].parent.exists()
    if explicit_root:
        assert roots[0].parent.parent == scratch.resolve()
    else:
        assert roots[0].parent.name.startswith("coderepair-shadow-")
        assert not scratch.exists()


def test_real_docker_preflight_fresh_project_scratch(request, monkeypatch):
    image_reference = request.getfixturevalue("docker_image")
    pinned, _, _ = pin_docker_image(replace(CONFIG, docker_image=image_reference))
    actual_create = runner.create_workspace
    roots = []

    def create(manifest, destination):
        assert not destination.exists()
        assert destination.parent.parent == (ROOT / ".coderepair-tmp").resolve()
        roots.append(destination)
        return actual_create(manifest, destination)

    monkeypatch.setattr(runner, "create_workspace", create)
    runner.docker_execution_preflight(MANIFEST, pinned)
    assert len(roots) == 1
    assert not roots[0].parent.exists()
