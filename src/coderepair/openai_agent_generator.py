"""Synchronous OpenAI Responses adapter for one typed agent action."""

import math
from time import perf_counter
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from coderepair.agent_generation import AgentStepResult
from coderepair.agent_protocol import (
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
)
from coderepair.file_changes import FileChange
from coderepair.generation import GenerationUsage


class _OpenAIFileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str


class _ReadFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["read_file"]
    path: str


class _ApplyFileChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["apply_file_changes"]
    changes: list[_OpenAIFileChange]


class _RunReproduction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["run_reproduction"]


class _RunFullTests(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["run_full_tests"]


class _RunLint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["run_lint"]


class _Finish(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["finish"]


class _OpenAIAgentStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: (
        _ReadFile
        | _ApplyFileChanges
        | _RunReproduction
        | _RunFullTests
        | _RunLint
        | _Finish
    )


class OpenAIAgentStepGenerator:
    """Convert one Responses request into one provider-neutral agent step."""

    def __init__(
        self,
        client: OpenAI,
        *,
        model: str,
        reasoning_effort: str,
        max_output_tokens: int,
        request_timeout_seconds: float,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if not isinstance(reasoning_effort, str) or not reasoning_effort.strip():
            raise ValueError("reasoning_effort must be a non-empty string")
        if (
            isinstance(max_output_tokens, bool)
            or not isinstance(max_output_tokens, int)
            or max_output_tokens <= 0
        ):
            raise ValueError("max_output_tokens must be a positive integer")
        if isinstance(request_timeout_seconds, bool) or not isinstance(
            request_timeout_seconds, (int, float)
        ):
            raise ValueError("request_timeout_seconds must be a positive finite number")
        try:
            timeout = float(request_timeout_seconds)
        except OverflowError as error:
            raise ValueError(
                "request_timeout_seconds must be a positive finite number"
            ) from error
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("request_timeout_seconds must be a positive finite number")

        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._request_timeout_seconds = timeout

    def __call__(self, prompt: str) -> AgentStepResult:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        request_client = self._client.with_options(
            max_retries=0,
            timeout=self._request_timeout_seconds,
        )
        started_at = perf_counter()
        response = request_client.responses.parse(
            model=self._model,
            reasoning={"effort": self._reasoning_effort},
            input=prompt,
            text_format=_OpenAIAgentStep,
            max_output_tokens=self._max_output_tokens,
        )
        latency_seconds = perf_counter() - started_at

        proposal = response.output_parsed
        if proposal is None:
            raise RuntimeError("OpenAI response has no parsed agent action")
        action = proposal.action
        if isinstance(action, _ReadFile):
            domain_action = ReadFileAction(path=action.path)
        elif isinstance(action, _ApplyFileChanges):
            domain_action = ApplyFileChangesAction(
                changes=tuple(
                    FileChange(path=change.path, content=change.content)
                    for change in action.changes
                )
            )
        elif isinstance(action, _RunReproduction):
            domain_action = RunReproductionAction()
        elif isinstance(action, _RunFullTests):
            domain_action = RunFullTestsAction()
        elif isinstance(action, _RunLint):
            domain_action = RunLintAction()
        elif isinstance(action, _Finish):
            domain_action = FinishAction()
        else:
            raise RuntimeError("unsupported parsed agent action")

        usage = response.usage
        generation_usage = (
            GenerationUsage(None, None, None)
            if usage is None
            else GenerationUsage(
                usage.input_tokens,
                usage.output_tokens,
                usage.total_tokens,
            )
        )
        return AgentStepResult(
            action=domain_action,
            usage=generation_usage,
            latency_seconds=latency_seconds,
            provider="openai",
            model=response.model or self._model,
        )
