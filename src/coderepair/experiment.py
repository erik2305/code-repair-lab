"""Raw paired-experiment records and small local provenance checks."""

import json
import subprocess
from dataclasses import asdict, dataclass, field, replace
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal, TextIO

from coderepair.agent_evidence import (
    ShadowPrefixResult,
    classify_iterative_occurrence,
    observation_evidence,
    patch_metadata,
)
from coderepair.agent_loop import AgentRunResult
from coderepair.agent_protocol import (
    AgentAction,
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
)
from coderepair.baseline import SingleShotResult
from coderepair.docker_runner import CommandResult
from coderepair.evaluator import EvaluationResult
from coderepair.openrouter_response import openrouter_routing_policy
from coderepair.run_config import AgentLimits, RunConfig
from coderepair.run_telemetry import (
    telemetry_from_agent_run,
    telemetry_from_single_shot,
)

Strategy = Literal["baseline", "agent"]


def resolved_dependency_versions() -> tuple[tuple[str, str], ...]:
    """Resolve required installed versions without inventing missing values."""
    try:
        return tuple((name, version(name)) for name in ("openai", "mcp", "pydantic"))
    except PackageNotFoundError as error:
        raise RuntimeError("required experiment dependency is not installed") from error


@dataclass(frozen=True, slots=True)
class ExperimentProvenance:
    """Observed identifiers needed to interpret one manual experiment."""

    experiment_id: str
    git_commit: str
    docker_image_id: str
    docker_repo_digests: tuple[str, ...]
    python_version: str
    platform: str
    dependency_versions: tuple[tuple[str, str], ...] = field(
        default_factory=resolved_dependency_versions
    )
    configured_docker_image: str | None = None


def counterbalanced_order(
    task_index: int, repetition: int
) -> tuple[Strategy, Strategy]:
    """Alternate first strategy by task and one-based repetition."""
    if (task_index + repetition - 1) % 2 == 0:
        return ("baseline", "agent")
    return ("agent", "baseline")


def require_clean_git(project_root: Path) -> str:
    """Return HEAD only when tracked and untracked repository state is clean."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("could not inspect Git worktree") from error
    if commit.returncode != 0 or not commit.stdout.strip() or status.returncode != 0:
        raise RuntimeError("could not determine a clean Git commit")
    if status.stdout.strip():
        raise RuntimeError("Git worktree is dirty; commit or stash changes first")
    return commit.stdout.strip()


def inspect_docker_image(image: str) -> tuple[str, tuple[str, ...]]:
    """Read the configured image ID and any repository digests without building it."""
    try:
        inspection = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"could not inspect Docker image {image}") from error
    if inspection.returncode != 0:
        raise RuntimeError(f"Docker image {image} is unavailable")
    try:
        images = json.loads(inspection.stdout)
        if not isinstance(images, list) or len(images) != 1:
            raise ValueError("expected one image")
        image_id = images[0]["Id"]
        digests = images[0].get("RepoDigests") or []
        if not isinstance(image_id, str) or not image_id.strip():
            raise ValueError("missing image ID")
        if not isinstance(digests, list) or any(
            not isinstance(digest, str) for digest in digests
        ):
            raise ValueError("invalid repository digests")
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError(
            f"Docker image {image} has invalid inspection data"
        ) from error
    return image_id, tuple(digests)


def pin_docker_image(config: RunConfig) -> tuple[RunConfig, str, tuple[str, ...]]:
    """Resolve a mutable tag once; use the returned config for all executions."""
    image_id, digests = inspect_docker_image(config.docker_image)
    return replace(config, docker_image=image_id), image_id, digests


def open_new_output(path: Path) -> TextIO:
    """Create a JSONL destination exclusively; its parent must already exist."""
    if not path.parent.is_dir():
        raise ValueError("output parent directory does not exist")
    try:
        return path.open("x", encoding="utf-8", newline="\n")
    except FileExistsError as error:
        raise ValueError("output file already exists") from error


def serialize_action(action: AgentAction) -> dict[str, object]:
    """Record intent and paths only, never generated source contents."""
    if isinstance(action, ReadFileAction):
        return {"type": "read_file", "paths": [action.path]}
    if isinstance(action, ApplyFileChangesAction):
        return {
            "type": "apply_file_changes",
            "paths": [change.path for change in action.changes],
        }
    if isinstance(action, RunReproductionAction):
        return {"type": "run_reproduction", "paths": []}
    if isinstance(action, RunFullTestsAction):
        return {"type": "run_full_tests", "paths": []}
    if isinstance(action, RunLintAction):
        return {"type": "run_lint", "paths": []}
    if isinstance(action, FinishAction):
        return {"type": "finish", "paths": []}
    raise ValueError("unknown agent action type")


def baseline_record(
    result: SingleShotResult,
    *,
    provenance: ExperimentProvenance,
    config: RunConfig,
    limits: AgentLimits,
    task_id: str,
    repetition: int,
    position: int,
    started_utc: str,
    finished_utc: str,
    lint_configured: bool,
) -> dict[str, object]:
    """Serialize one completed baseline attempt using existing telemetry semantics."""
    record = _common_record(
        provenance,
        config,
        limits,
        task_id,
        repetition,
        "baseline",
        position,
        started_utc,
        finished_utc,
    )
    record.update(asdict(telemetry_from_single_shot(result)))
    record.update(_evaluation_fields(result.evaluation, lint_configured))
    generation = result.generation
    record.update(
        mutation_applied=result.mutation_applied,
        mutation_error=result.mutation_error,
        proposed_change_paths=[change.path for change in result.changes],
        generation_provider=generation.provider,
        returned_model=generation.model,
        routed_provider=generation.routed_provider,
        generation_input_tokens=generation.usage.input_tokens,
        generation_output_tokens=generation.usage.output_tokens,
        generation_total_tokens=generation.usage.total_tokens,
        generation_reported_cost_usd=generation.reported_cost_usd,
        generation_latency_seconds=generation.latency_seconds,
        generation_prompt_sha256=generation.prompt_sha256,
        generation_cached_input_tokens=generation.usage.cached_input_tokens,
        generation_reasoning_output_tokens=generation.usage.reasoning_output_tokens,
        initial_context_sha256=result.initial_context_sha256,
    )
    return record


def agent_record(
    result: AgentRunResult,
    *,
    provenance: ExperimentProvenance,
    config: RunConfig,
    limits: AgentLimits,
    task_id: str,
    repetition: int,
    position: int,
    started_utc: str,
    finished_utc: str,
    lint_configured: bool,
    shadow_prefixes: tuple[ShadowPrefixResult, ...] = (),
) -> dict[str, object]:
    """Serialize one completed agent attempt without prompts or tool content."""
    record = _common_record(
        provenance,
        config,
        limits,
        task_id,
        repetition,
        "agent",
        position,
        started_utc,
        finished_utc,
    )
    record.update(asdict(telemetry_from_agent_run(result)))
    record.update(_evaluation_fields(result.evaluation, lint_configured))
    record["termination_reason"] = result.termination_reason
    record["initial_context_sha256"] = result.initial_context_sha256
    record["iterative_occurrence"] = classify_iterative_occurrence(result)
    record["shadow_prefixes"] = [asdict(prefix) for prefix in shadow_prefixes]
    generations: list[dict[str, object]] = []
    for step, generation in enumerate(result.generations, start=1):
        action = serialize_action(generation.action)
        patch_hash, changes = (
            patch_metadata(generation.action.changes)
            if isinstance(generation.action, ApplyFileChangesAction)
            else (None, [])
        )
        generations.append(
            {
                "step": step,
                "action_type": action["type"],
                "action_paths": action["paths"],
                "gateway_provider": generation.provider,
                "returned_model": generation.model,
                "routed_provider": generation.routed_provider,
                "input_tokens": generation.usage.input_tokens,
                "output_tokens": generation.usage.output_tokens,
                "total_tokens": generation.usage.total_tokens,
                "reported_cost_usd": generation.reported_cost_usd,
                "latency_seconds": generation.latency_seconds,
                "cached_input_tokens": generation.usage.cached_input_tokens,
                "reasoning_output_tokens": generation.usage.reasoning_output_tokens,
                "prompt_sha256": generation.prompt_sha256,
                "patch_sha256": patch_hash,
                "changes": changes,
            }
        )
    record["generations"] = generations
    record["transcript"] = [
        {
            "step": step,
            **observation_evidence(entry),
        }
        for step, entry in enumerate(result.transcript, start=1)
    ]
    return record


def _common_record(
    provenance: ExperimentProvenance,
    config: RunConfig,
    limits: AgentLimits,
    task_id: str,
    repetition: int,
    strategy: Strategy,
    position: int,
    started_utc: str,
    finished_utc: str,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "experiment_id": provenance.experiment_id,
        "task_id": task_id,
        "repetition": repetition,
        "strategy": strategy,
        "execution_position_within_pair": position,
        "timestamp_started_utc": started_utc,
        "timestamp_finished_utc": finished_utc,
        "git_commit": provenance.git_commit,
        "docker_image_id": provenance.docker_image_id,
        "configured_docker_image": (
            provenance.configured_docker_image or config.docker_image
        ),
        "docker_repo_digests": list(provenance.docker_repo_digests),
        "python_version": provenance.python_version,
        "platform": provenance.platform,
        "dependency_versions": dict(provenance.dependency_versions),
        "routing_policy": openrouter_routing_policy(),
        "configured_agent_limits": asdict(limits),
        "agent_limits": asdict(limits) if strategy == "agent" else None,
        **asdict(config),
        "requested_model": config.model,
    }


def _evaluation_fields(
    evaluation: EvaluationResult | None, lint_configured: bool
) -> dict[str, object]:
    return {
        "evaluation_success": evaluation.success if evaluation is not None else None,
        "writable_paths_respected": (
            evaluation.writable_paths_respected if evaluation is not None else None
        ),
        "unauthorized_changes": (
            list(evaluation.unauthorized_changes) if evaluation is not None else None
        ),
        "protected_paths_unchanged": (
            evaluation.protected_paths_unchanged if evaluation is not None else None
        ),
        "protected_changes": (
            list(evaluation.protected_changes) if evaluation is not None else None
        ),
        "reproduction": _command_fields(
            evaluation.reproduction if evaluation is not None else None, True
        ),
        "full_test": _command_fields(
            evaluation.full_test if evaluation is not None else None, True
        ),
        "lint": _command_fields(
            evaluation.lint if evaluation is not None else None, lint_configured
        ),
    }


def _command_fields(
    command: CommandResult | None, configured: bool
) -> dict[str, object]:
    return {
        "configured": configured,
        "present": command is not None,
        "exit_code": command.exit_code if command is not None else None,
        "timed_out": command.timed_out if command is not None else None,
        "duration_seconds": command.duration_seconds if command is not None else None,
    }
