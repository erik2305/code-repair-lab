"""Bounded cumulative repair loop over the existing workspace-scoped MCP tools."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Literal

from mcp import Client

from coderepair.agent_generation import AgentStepGenerator, AgentStepResult
from coderepair.agent_prompt import render_agent_step_prompt, render_agent_transcript
from coderepair.agent_protocol import (
    AgentObservation,
    AgentToolAction,
    AgentTranscriptEntry,
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    tool_name_for_action,
)
from coderepair.evaluator import EvaluationResult, evaluate_workspace
from coderepair.mcp_server import build_mcp_server
from coderepair.repair_context import build_initial_context
from coderepair.run_config import AgentLimits, RunConfig
from coderepair.tasks import load_task
from coderepair.workspace import Workspace

AgentTerminationReason = Literal[
    "finish",
    "model_call_limit",
    "tool_call_limit",
    "transcript_limit",
]


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    """One run; duration excludes manifest validation and workspace creation."""

    generations: tuple[AgentStepResult, ...]
    transcript: tuple[AgentTranscriptEntry, ...]
    termination_reason: AgentTerminationReason
    evaluation: EvaluationResult
    duration_seconds: float

    @property
    def success(self) -> bool:
        return self.evaluation.success

    @property
    def model_calls(self) -> int:
        return len(self.generations)

    @property
    def tool_calls(self) -> int:
        return len(self.transcript)


def run_agentic_repair(
    task_manifest: Path,
    workspace: Workspace,
    *,
    generator: AgentStepGenerator,
    config: RunConfig,
    limits: AgentLimits,
) -> AgentRunResult:
    """Time context, MCP/model steps and evaluation after task validation."""
    if load_task(task_manifest) != workspace.task:
        raise ValueError("workspace task does not match the supplied task manifest")

    started_at = perf_counter()
    context = build_initial_context(
        workspace,
        max_file_bytes=config.max_file_bytes,
        max_total_bytes=config.max_total_bytes,
    )
    server = build_mcp_server(
        workspace,
        image=config.docker_image,
        timeout_seconds=config.evaluator_timeout_seconds,
    )

    async def run_steps() -> tuple[
        tuple[AgentStepResult, ...],
        tuple[AgentTranscriptEntry, ...],
        AgentTerminationReason,
    ]:
        generations: list[AgentStepResult] = []
        transcript: list[AgentTranscriptEntry] = []
        generator_error: Exception | None = None
        async with Client(server, raise_exceptions=True) as client:
            while len(generations) < limits.max_model_calls:
                tool_calls_remaining = limits.max_tool_calls - len(transcript)
                prompt = render_agent_step_prompt(
                    context,
                    tuple(transcript),
                    model_calls_remaining=limits.max_model_calls - len(generations),
                    tool_calls_remaining=tool_calls_remaining,
                )
                try:
                    generation = generator(prompt)
                    if not isinstance(generation, AgentStepResult):
                        raise ValueError("generator must return an AgentStepResult")
                except Exception as error:
                    # Exit the MCP task group cleanly, then propagate the original
                    # provider/programming exception without an ExceptionGroup wrapper.
                    generator_error = error
                    break
                generations.append(generation)
                action = generation.action
                if isinstance(action, FinishAction):
                    reason: AgentTerminationReason = "finish"
                    break
                if tool_calls_remaining == 0:
                    reason = "tool_call_limit"
                    break

                name = tool_name_for_action(action)
                result = await client.call_tool(name, _tool_arguments(action))
                if result.is_error:
                    content = "\n".join(
                        block.text for block in result.content if block.type == "text"
                    )
                elif result.structured_content is not None:
                    content = json.dumps(
                        result.structured_content,
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                else:
                    content = "\n".join(
                        block.text for block in result.content if block.type == "text"
                    )
                transcript.append(
                    AgentTranscriptEntry(
                        action,
                        AgentObservation(name, content, result.is_error),
                    )
                )
                # The final oversized entry remains in the run record, but it must
                # never be supplied to another model call.
                transcript_bytes = len(
                    render_agent_transcript(tuple(transcript)).encode("utf-8")
                )
                if transcript_bytes > limits.max_transcript_bytes:
                    reason = "transcript_limit"
                    break
            else:
                reason = "model_call_limit"
        if generator_error is not None:
            raise generator_error
        return tuple(generations), tuple(transcript), reason

    generations, transcript, reason = asyncio.run(run_steps())
    evaluation = evaluate_workspace(
        task_manifest,
        workspace,
        image=config.docker_image,
        timeout_seconds=config.evaluator_timeout_seconds,
    )
    return AgentRunResult(
        generations, transcript, reason, evaluation, perf_counter() - started_at
    )


def _tool_arguments(action: AgentToolAction) -> dict[str, object]:
    if isinstance(action, ReadFileAction):
        return {"path": action.path}
    if isinstance(action, ApplyFileChangesAction):
        return {
            "changes": [
                {"path": change.path, "content": change.content}
                for change in action.changes
            ]
        }
    return {}
