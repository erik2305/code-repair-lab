import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

import coderepair.docker_runner as docker_runner
from coderepair.docker_runner import run_in_docker
from coderepair.tasks import load_task
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_001_MANIFEST = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001" / "task.yaml"
SANDBOX_IMAGE = "coderepair-lab-sandbox:dev"


def validation_workspace(tmp_path: Path) -> Workspace:
    return Workspace(task=load_task(DEV_001_MANIFEST), root=tmp_path)


@pytest.mark.parametrize(
    "argv",
    [[], "python -V", ["python", ""], ["python", 3]],
)
def test_rejects_invalid_argv(tmp_path: Path, argv: object) -> None:
    with pytest.raises(ValueError, match="argv|element"):
        run_in_docker(
            validation_workspace(tmp_path),
            argv,  # type: ignore[arg-type]
            image=SANDBOX_IMAGE,
            timeout_seconds=1,
        )


@pytest.mark.parametrize("timeout_seconds", [0, -1])
def test_rejects_non_positive_timeout(
    tmp_path: Path, timeout_seconds: float
) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        run_in_docker(
            validation_workspace(tmp_path),
            ["python", "-V"],
            image=SANDBOX_IMAGE,
            timeout_seconds=timeout_seconds,
        )


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


@pytest.fixture
def docker_workspace(tmp_path: Path, docker_image: str) -> Workspace:
    workspace = create_workspace(DEV_001_MANIFEST, tmp_path / "workspace")
    yield workspace
    if workspace.root.exists():
        destroy_workspace(workspace)


def test_executes_inside_workspace(
    docker_workspace: Workspace, docker_image: str
) -> None:
    result = run_in_docker(
        docker_workspace,
        [
            "python",
            "-c",
            "from pathlib import Path; Path('marker.txt').write_text('created')",
        ],
        image=docker_image,
        timeout_seconds=10,
    )

    assert result.exit_code == 0
    assert (docker_workspace.root / "marker.txt").read_text() == "created"


def test_captures_output_and_success(
    docker_workspace: Workspace, docker_image: str
) -> None:
    result = run_in_docker(
        docker_workspace,
        ["python", "-c", "print('hello')"],
        image=docker_image,
        timeout_seconds=10,
    )

    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert not result.timed_out
    assert result.duration_seconds >= 0


def test_returns_non_zero_exit_code(
    docker_workspace: Workspace, docker_image: str
) -> None:
    result = run_in_docker(
        docker_workspace,
        ["python", "-c", "raise SystemExit(7)"],
        image=docker_image,
        timeout_seconds=10,
    )

    assert result.exit_code == 7
    assert not result.timed_out


def test_timeout_removes_container(
    docker_workspace: Workspace,
    docker_image: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = uuid.uuid4()
    container_name = f"coderepair-lab-{execution_id.hex}"
    monkeypatch.setattr(docker_runner.uuid, "uuid4", lambda: execution_id)

    result = run_in_docker(
        docker_workspace,
        ["python", "-c", "import time; time.sleep(30)"],
        image=docker_image,
        timeout_seconds=1,
    )

    assert result.timed_out
    assert result.exit_code is None

    inspection = subprocess.run(
        ["docker", "container", "inspect", container_name],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    assert inspection.returncode != 0
