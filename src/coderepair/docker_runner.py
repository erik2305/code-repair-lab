"""Run trusted argv commands in a constrained Docker container."""

import math
import subprocess
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from time import monotonic

from coderepair.workspace import Workspace


@dataclass(frozen=True, slots=True)
class CommandResult:
    """The captured result of one container command."""

    argv: tuple[str, ...]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float


def run_in_docker(
    workspace: Workspace,
    argv: Sequence[str],
    *,
    image: str,
    timeout_seconds: float,
) -> CommandResult:
    """Run *argv* in a Docker container bound to *workspace*."""
    command_argv = _validate_argv(argv)
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("timeout_seconds must be a positive finite number")
    if not isinstance(image, str) or not image.strip():
        raise ValueError("image must be a non-empty string")

    container_name = f"coderepair-lab-{uuid.uuid4().hex}"
    docker_argv = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "512m",
        "--cpus",
        "1",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--mount",
        f"type=bind,source={workspace.root},target=/workspace",
        "--workdir",
        "/workspace",
        image,
        *command_argv,
    ]

    started_at = monotonic()
    try:
        completed = subprocess.run(
            docker_argv,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        _force_remove_container(container_name)
        return CommandResult(
            argv=command_argv,
            exit_code=None,
            stdout=_captured_text(error.stdout),
            stderr=_captured_text(error.stderr),
            timed_out=True,
            duration_seconds=monotonic() - started_at,
        )

    return CommandResult(
        argv=command_argv,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
        duration_seconds=monotonic() - started_at,
    )


def _validate_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if isinstance(argv, (str, bytes)) or not argv:
        raise ValueError("argv must be a non-empty sequence of arguments")
    if any(not isinstance(argument, str) or not argument.strip() for argument in argv):
        raise ValueError("every argv element must be a non-empty string")
    return tuple(argv)


def _force_remove_container(container_name: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _captured_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
