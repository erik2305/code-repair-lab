"""Provider-independent single-shot repair baseline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from coderepair.evaluator import EvaluationResult, evaluate_workspace
from coderepair.file_changes import FileChange, apply_file_changes
from coderepair.generation import GenerationResult
from coderepair.repair_context import (
    InitialRepairContext,
    build_initial_context,
    render_initial_context,
)
from coderepair.tasks import load_task
from coderepair.workspace import Workspace


class RepairGenerator(Protocol):
    """One provider-independent proposal from one prompt."""

    def __call__(self, prompt: str) -> GenerationResult: ...


@dataclass(frozen=True, slots=True)
class SingleShotResult:
    """One proposal, its mutation outcome, and optional final evaluation."""

    generation: GenerationResult
    mutation_applied: bool
    mutation_error: str | None
    evaluation: EvaluationResult | None

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
        render_initial_context(context)
        + "\nSINGLE-SHOT REPAIR\n"
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
    max_file_bytes: int,
    max_total_bytes: int,
    image: str,
    timeout_seconds: float,
) -> SingleShotResult:
    """Run one proposal on a fresh disposable workspace; caller owns its lifecycle."""
    if load_task(task_manifest) != workspace.task:
        raise ValueError("workspace task does not match the supplied task manifest")

    context = build_initial_context(
        workspace, max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes
    )
    prompt = render_single_shot_prompt(context)
    generation = generator(prompt)
    if not isinstance(generation, GenerationResult):
        raise ValueError("generator must return a GenerationResult")

    try:
        apply_file_changes(workspace, generation.changes)
    except (ValueError, OSError) as error:
        return SingleShotResult(
            generation, False, _safe_mutation_error(error, workspace.root), None
        )

    evaluation = evaluate_workspace(
        task_manifest,
        workspace,
        image=image,
        timeout_seconds=timeout_seconds,
    )
    return SingleShotResult(generation, True, None, evaluation)


def _safe_mutation_error(error: ValueError | OSError, root: Path) -> str:
    if isinstance(error, OSError):
        return "workspace file access failed"
    message = str(error)
    root_text = str(root)
    for separator in ("/", "\\"):
        message = message.replace(root_text + separator, "")
    return message.replace(root_text, "workspace")
