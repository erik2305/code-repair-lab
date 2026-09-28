"""Small shared request and response helpers for OpenRouter Responses adapters."""

import math
from collections.abc import Mapping
from typing import Any

from coderepair.generation import GenerationUsage

_ROUTING = {"allow_fallbacks": True, "require_parameters": True}
_METADATA_HEADER = {"X-OpenRouter-Metadata": "enabled"}


def _validate_options(
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
    request_timeout_seconds: float,
) -> float:
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
    return timeout


def _parse_once(
    client: Any,
    *,
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
    timeout: float,
    prompt: str,
    text_format: type,
) -> Any:
    """Issue exactly one SDK request, with only same-model provider failover."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    request_client = client.with_options(max_retries=0, timeout=timeout)
    return request_client.responses.parse(
        model=model,
        reasoning={"effort": reasoning_effort},
        input=prompt,
        text_format=text_format,
        max_output_tokens=max_output_tokens,
        extra_body={"provider": _ROUTING.copy()},
        extra_headers=_METADATA_HEADER.copy(),
    )


def _field(value: Any, name: str) -> Any:
    """Read documented fields or public Pydantic extra fields."""
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(name)
    attribute = getattr(value, name, None)
    if attribute is not None:
        return attribute
    extras = getattr(value, "model_extra", None)
    return extras.get(name) if isinstance(extras, Mapping) else None


def _usage(response: Any) -> GenerationUsage:
    usage = _field(response, "usage")
    if usage is None:
        return GenerationUsage(None, None, None)
    return GenerationUsage(
        _field(usage, "input_tokens"),
        _field(usage, "output_tokens"),
        _field(usage, "total_tokens"),
    )


def _reported_cost(response: Any) -> float | None:
    return _field(_field(response, "usage"), "cost")


def _routed_provider(response: Any) -> str | None:
    metadata = _field(response, "openrouter_metadata")
    endpoints = _field(_field(metadata, "endpoints"), "available")
    if not isinstance(endpoints, (list, tuple)):
        return None
    selected = [
        endpoint for endpoint in endpoints if _field(endpoint, "selected") is True
    ]
    if len(selected) != 1:
        return None
    provider = _field(selected[0], "provider")
    return provider if isinstance(provider, str) and provider.strip() else None
