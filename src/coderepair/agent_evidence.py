"""Prospective, source-free evidence from completed agent runs."""

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from coderepair.agent_loop import AgentRunResult
from coderepair.agent_protocol import (
    AgentTranscriptEntry,
    ApplyFileChangesAction,
    ReadFileAction,
)
from coderepair.evaluator import (
    EvaluationResult,
    evaluate_workspace,
    workspace_state_sha256,
)
from coderepair.file_changes import FileChange, apply_file_changes
from coderepair.workspace import create_workspace, destroy_workspace

_EXECUTION_TOOLS = frozenset({"run_reproduction", "run_full_tests", "run_lint"})


def patch_metadata(changes: tuple[FileChange, ...]) -> tuple[str, list[dict[str, str]]]:
    """Hash a sorted path/content-digest proposal, without retaining source text."""
    files = sorted(
        (
            {
                "path": change.path,
                "content_sha256": sha256(change.content.encode("utf-8")).hexdigest(),
            }
            for change in changes
        ),
        key=lambda item: (item["path"], item["content_sha256"]),
    )
    payload = json.dumps(
        files, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256(payload.encode("utf-8")).hexdigest(), files


def observation_evidence(entry: AgentTranscriptEntry) -> dict[str, object]:
    """Keep only execution outcome metadata and a digest of model-visible text."""
    observation = entry.observation
    exit_code: int | None = None
    timed_out: bool | None = None
    if observation.tool in _EXECUTION_TOOLS and not observation.is_error:
        try:
            structured = json.loads(observation.content)
        except json.JSONDecodeError:
            structured = None
        if isinstance(structured, dict):
            raw_exit = structured.get("exit_code")
            raw_timeout = structured.get("timed_out")
            if type(raw_exit) is int:
                exit_code = raw_exit
            if type(raw_timeout) is bool:
                timed_out = raw_timeout
    return {
        "tool": observation.tool,
        "is_error": observation.is_error,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "observation_sha256": sha256(observation.content.encode("utf-8")).hexdigest(),
    }


def classify_iterative_occurrence(result: AgentRunResult) -> str:
    """Classify trace occurrence only; never infer cross-arm iterative value."""
    if not result.evaluation.success:
        return "none"
    patches = [
        (index, patch_metadata(entry.action.changes)[0])
        for index, entry in enumerate(result.transcript)
        if isinstance(entry.action, ApplyFileChangesAction)
        and not entry.observation.is_error
    ]
    if len(patches) == 1:
        return "tool_assisted_one_patch"
    saw_context_refinement = False
    for (first_index, first_hash), (second_index, second_hash) in zip(
        patches, patches[1:]
    ):
        if first_hash == second_hash:
            continue
        intervening = result.transcript[first_index + 1 : second_index]
        failing_diagnostic = any(
            evidence["tool"] in _EXECUTION_TOOLS
            and not evidence["is_error"]
            and (
                evidence["timed_out"] is True
                or evidence["exit_code"] is not None
                and evidence["exit_code"] != 0
            )
            for evidence in map(observation_evidence, intervening)
        )
        if failing_diagnostic:
            return "feedback_responsive_iteration"
        if any(
            isinstance(entry.action, ReadFileAction) and not entry.observation.is_error
            for entry in intervening
        ):
            saw_context_refinement = True
    return "context_refinement_iteration" if saw_context_refinement else "none"


@dataclass(frozen=True, slots=True)
class ShadowPrefixResult:
    patch_index: int
    evaluation_success: bool
    writable_paths_respected: bool
    protected_paths_unchanged: bool
    reproduction_exit_code: int | None
    reproduction_timed_out: bool | None
    full_test_exit_code: int | None
    full_test_timed_out: bool | None
    lint_exit_code: int | None
    lint_timed_out: bool | None
    workspace_state_sha256: str


def shadow_evaluate_prefixes(
    task_manifest: Path,
    result: AgentRunResult,
    *,
    image: str,
    timeout_seconds: float,
) -> tuple[ShadowPrefixResult, ...]:
    """Replay successful mutation prefixes after the live run, off-transcript."""
    with TemporaryDirectory(prefix="coderepair-shadow-") as temporary:
        workspace = create_workspace(task_manifest, Path(temporary) / "workspace")
        try:
            measurements: list[ShadowPrefixResult] = []
            for entry in result.transcript:
                if (
                    not isinstance(entry.action, ApplyFileChangesAction)
                    or entry.observation.is_error
                ):
                    continue
                apply_file_changes(workspace, entry.action.changes)
                state_digest = workspace_state_sha256(workspace.root)
                evaluation = evaluate_workspace(
                    task_manifest,
                    workspace,
                    image=image,
                    timeout_seconds=timeout_seconds,
                )
                measurements.append(
                    _shadow_measurement(len(measurements) + 1, evaluation, state_digest)
                )
            return tuple(measurements)
        finally:
            destroy_workspace(workspace)


def _shadow_measurement(
    patch_index: int, evaluation: EvaluationResult, state_digest: str
) -> ShadowPrefixResult:
    return ShadowPrefixResult(
        patch_index=patch_index,
        evaluation_success=evaluation.success,
        writable_paths_respected=evaluation.writable_paths_respected,
        protected_paths_unchanged=evaluation.protected_paths_unchanged,
        reproduction_exit_code=(
            evaluation.reproduction.exit_code if evaluation.reproduction else None
        ),
        reproduction_timed_out=(
            evaluation.reproduction.timed_out if evaluation.reproduction else None
        ),
        full_test_exit_code=evaluation.full_test.exit_code
        if evaluation.full_test
        else None,
        full_test_timed_out=evaluation.full_test.timed_out
        if evaluation.full_test
        else None,
        lint_exit_code=evaluation.lint.exit_code if evaluation.lint else None,
        lint_timed_out=evaluation.lint.timed_out if evaluation.lint else None,
        workspace_state_sha256=state_digest,
    )
