"""Synchronous OpenAI Responses adapter for repair proposals."""

import math
from time import perf_counter

from openai import OpenAI
from pydantic import BaseModel, ConfigDict

from coderepair.file_changes import FileChange
from coderepair.generation import GenerationResult, GenerationUsage


class _OpenAIFileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str


class _OpenAIRepairProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: list[_OpenAIFileChange]


class OpenAIRepairGenerator:
    """Turn one Responses API request into one provider-neutral proposal."""

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

    def __call__(self, prompt: str) -> GenerationResult:
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
            text_format=_OpenAIRepairProposal,
            max_output_tokens=self._max_output_tokens,
        )
        latency_seconds = perf_counter() - started_at

        proposal = response.output_parsed
        if proposal is None:
            raise RuntimeError("OpenAI response has no parsed repair proposal")
        changes = tuple(
            FileChange(path=change.path, content=change.content)
            for change in proposal.changes
        )
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
        return GenerationResult(
            changes=changes,
            usage=generation_usage,
            latency_seconds=latency_seconds,
            provider="openai",
            model=response.model or self._model,
        )
