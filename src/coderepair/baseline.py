"""Provider-independent single-shot repair baseline."""

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Protocol

from coderepair.evaluator import EvaluationResult, evaluate_workspace
from coderepair.file_changes import FileChange, apply_file_changes
from coderepair.generation import GenerationResult
from coderepair.repair_context import (
    InitialRepairContext,
    build_initial_context,
    initial_context_sha256,
    render_initial_context,
)
from coderepair.run_config import RunConfig
from coderepair.tasks import load_task
from coderepair.workspace import Workspace


class RepairGenerator(Protocol):
    """One provider-independent proposal from one prompt."""

    def __call__(self, prompt: str) -> GenerationResult: ...


@dataclass(frozen=True, slots=True)
class SingleShotResult:
    """One proposal; duration excludes manifest validation and workspace creation."""

    generation: GenerationResult
    mutation_applied: bool
    mutation_error: str | None
    evaluation: EvaluationResult | None
    duration_seconds: float
    initial_context_sha256: str | None = None

    @property
    def changes(self) -> tuple[FileChange, ...]:
        return self.generation.changes

    @property
    def success(self) -> bool:
        return (
            self.mutation_applied
            and self.evaluation is not None
            and self.evaluation.success
        )


def render_single_shot_prompt(context: InitialRepairContext) -> str:
    """Add one-attempt instructions to the exact shared initial context."""
    return (
        render_initial_context(context) + "\nSINGLE-SHOT REPAIR\n"
        "Diagnose the bug from the supplied context and propose final file changes "
        "in one attempt. Change only writable files. Protected files may be inspected "
        "but must not be changed. There will be no iterative test feedback or "
        "additional repository inspection.\n"
    )


def run_single_shot_baseline(
    task_manifest: Path,
    workspace: Workspace,
    *,
    generator: RepairGenerator,
    config: RunConfig,
) -> SingleShotResult:
    """Time context, generation, mutation and any evaluation after task validation."""
    if load_task(task_manifest) != workspace.task:
        raise ValueError("workspace task does not match the supplied task manifest")

    started_at = perf_counter()
    context = build_initial_context(
        workspace,
        max_file_bytes=config.max_file_bytes,
        max_total_bytes=config.max_total_bytes,
    )
    context_digest = initial_context_sha256(context)
    prompt = render_single_shot_prompt(context)
    generation = generator(prompt)
    if not isinstance(generation, GenerationResult):
        raise ValueError("generator must return a GenerationResult")

    try:
        apply_file_changes(workspace, generation.changes)
    except (ValueError, OSError) as error:
        return SingleShotResult(
            generation,
            False,
            _safe_mutation_error(error, workspace.root),
            None,
            perf_counter() - started_at,
            context_digest,
        )

    evaluation = evaluate_workspace(
        task_manifest,
        workspace,
        image=config.docker_image,
        timeout_seconds=config.evaluator_timeout_seconds,
    )
    return SingleShotResult(
        generation,
        True,
        None,
        evaluation,
        perf_counter() - started_at,
        context_digest,
    )


def _safe_mutation_error(error: ValueError | OSError, root: Path) -> str:
    if isinstance(error, OSError):
        return "workspace file access failed"
    message = str(error)
    root_text = str(root)
    for separator in ("/", "\\"):
        message = message.replace(root_text + separator, "")
    return message.replace(root_text, "workspace")
