"""OpenRouter Responses adapter for one structured repair proposal."""

from hashlib import sha256
from time import perf_counter

from openai import OpenAI

from coderepair.file_changes import FileChange
from coderepair.generation import GenerationResult
from coderepair.openrouter_response import (
    _field,
    _parse_once,
    _reported_cost,
    _routed_provider,
    _usage,
    _validate_options,
)
from coderepair.responses_schema import _RepairProposal


class OpenRouterRepairGenerator:
    """Generate one repair with a fixed model and same-model provider fallback."""

    def __init__(
        self,
        client: OpenAI,
        *,
        model: str,
        reasoning_effort: str,
        max_output_tokens: int,
        request_timeout_seconds: float,
    ) -> None:
        self._timeout = _validate_options(
            model, reasoning_effort, max_output_tokens, request_timeout_seconds
        )
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens

    def __call__(self, prompt: str) -> GenerationResult:
        started_at = perf_counter()
        response = _parse_once(
            self._client,
            model=self._model,
            reasoning_effort=self._reasoning_effort,
            max_output_tokens=self._max_output_tokens,
            timeout=self._timeout,
            prompt=prompt,
            text_format=_RepairProposal,
        )
        latency_seconds = perf_counter() - started_at
        proposal = response.output_parsed
        if proposal is None:
            raise RuntimeError("OpenRouter response has no parsed repair proposal")
        return GenerationResult(
            changes=tuple(
                FileChange(path=change.path, content=change.content)
                for change in proposal.changes
            ),
            usage=_usage(response),
            latency_seconds=latency_seconds,
            provider="openrouter",
            model=_field(response, "model") or self._model,
            reported_cost_usd=_reported_cost(response),
            routed_provider=_routed_provider(response),
            prompt_sha256=sha256(prompt.encode("utf-8")).hexdigest(),
        )
