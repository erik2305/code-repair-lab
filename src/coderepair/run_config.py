"""Chosen controls shared by repair runs and separate agent-only limits."""

import math
from dataclasses import dataclass


def _positive_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _positive_finite_number(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")


@dataclass(frozen=True, slots=True)
class RunConfig:
    """Trusted experimental controls common to baseline and agent runs."""

    model: str
    reasoning_effort: str
    max_output_tokens: int
    request_timeout_seconds: float
    evaluator_timeout_seconds: float
    max_file_bytes: int
    max_total_bytes: int
    docker_image: str

    def __post_init__(self) -> None:
        for name in ("model", "reasoning_effort", "docker_image"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("max_output_tokens", "max_file_bytes", "max_total_bytes"):
            _positive_integer(name, getattr(self, name))
        for name in ("request_timeout_seconds", "evaluator_timeout_seconds"):
            _positive_finite_number(name, getattr(self, name))
        if self.max_total_bytes < self.max_file_bytes:
            raise ValueError("max_total_bytes must be at least max_file_bytes")


@dataclass(frozen=True, slots=True)
class AgentLimits:
    """Budgets that apply only to an iterative agent."""

    max_model_calls: int
    max_tool_calls: int
    max_transcript_bytes: int

    def __post_init__(self) -> None:
        for name in ("max_model_calls", "max_tool_calls", "max_transcript_bytes"):
            _positive_integer(name, getattr(self, name))
