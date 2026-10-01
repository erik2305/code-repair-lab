"""Comparable raw measurements from completed repair strategy runs."""

import math
from dataclasses import dataclass

from coderepair.agent_loop import AgentRunResult
from coderepair.baseline import SingleShotResult


@dataclass(frozen=True, slots=True)
class RunTelemetry:
    """Evaluator success, call counts, provider usage, and strategy duration."""

    success: bool
    model_calls: int
    tool_calls: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    model_latency_seconds: float | None
    duration_seconds: float
    reported_cost_usd: float | None = None
    cached_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if type(self.success) is not bool:
            raise ValueError("success must be a bool")
        for name in ("model_calls", "tool_calls"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "reasoning_output_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        _validate_duration("model_latency_seconds", self.model_latency_seconds, True)
        _validate_duration("duration_seconds", self.duration_seconds, False)
        _validate_duration("reported_cost_usd", self.reported_cost_usd, True)


def telemetry_from_single_shot(result: SingleShotResult) -> RunTelemetry:
    """Map one completed baseline result without reinterpreting provider usage."""
    usage = result.generation.usage
    return RunTelemetry(
        success=result.evaluation.success if result.evaluation is not None else False,
        model_calls=1,
        tool_calls=0,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        model_latency_seconds=result.generation.latency_seconds,
        duration_seconds=result.duration_seconds,
        reported_cost_usd=result.generation.reported_cost_usd,
        cached_input_tokens=usage.cached_input_tokens,
        reasoning_output_tokens=usage.reasoning_output_tokens,
    )


def telemetry_from_agent_run(result: AgentRunResult) -> RunTelemetry:
    """Aggregate complete per-call measurements from a completed agent run."""
    return RunTelemetry(
        success=result.evaluation.success,
        model_calls=len(result.generations),
        tool_calls=len(result.transcript),
        input_tokens=_sum_complete(
            tuple(step.usage.input_tokens for step in result.generations)
        ),
        output_tokens=_sum_complete(
            tuple(step.usage.output_tokens for step in result.generations)
        ),
        total_tokens=_sum_complete(
            tuple(step.usage.total_tokens for step in result.generations)
        ),
        model_latency_seconds=_sum_complete(
            tuple(step.latency_seconds for step in result.generations)
        ),
        duration_seconds=result.duration_seconds,
        reported_cost_usd=_sum_complete(
            tuple(step.reported_cost_usd for step in result.generations)
        ),
        cached_input_tokens=_sum_complete(
            tuple(step.usage.cached_input_tokens for step in result.generations)
        ),
        reasoning_output_tokens=_sum_complete(
            tuple(step.usage.reasoning_output_tokens for step in result.generations)
        ),
    )


def _sum_complete(values: tuple[int | float | None, ...]) -> int | float | None:
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _validate_duration(name: str, value: float | None, optional: bool) -> None:
    if optional and value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
