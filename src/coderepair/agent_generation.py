"""Provider-neutral result of one agent action-generation request."""

import math
from dataclasses import dataclass
from typing import Protocol

from coderepair.agent_protocol import (
    AgentAction,
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
)
from coderepair.generation import GenerationUsage


@dataclass(frozen=True, slots=True)
class AgentStepResult:
    """One proposed action and its provider-reported telemetry."""

    action: AgentAction
    usage: GenerationUsage
    latency_seconds: float | None
    provider: str | None
    model: str | None
    reported_cost_usd: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.action,
            (
                ReadFileAction,
                ApplyFileChangesAction,
                RunReproductionAction,
                RunFullTestsAction,
                RunLintAction,
                FinishAction,
            ),
        ):
            raise ValueError("action must be an AgentAction")
        if not isinstance(self.usage, GenerationUsage):
            raise ValueError("usage must be a GenerationUsage")
        latency = self.latency_seconds
        if latency is not None and (
            isinstance(latency, bool)
            or not isinstance(latency, (int, float))
            or (isinstance(latency, float) and not math.isfinite(latency))
            or latency < 0
        ):
            raise ValueError(
                "latency_seconds must be a finite non-negative number or None"
            )
        for name in ("provider", "model"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")
        cost = self.reported_cost_usd
        if cost is not None:
            try:
                valid_cost = (
                    not isinstance(cost, bool)
                    and isinstance(cost, (int, float))
                    and math.isfinite(cost)
                    and cost >= 0
                )
            except OverflowError:
                valid_cost = False
            if not valid_cost:
                raise ValueError(
                    "reported_cost_usd must be a finite non-negative number or None"
                )


class AgentStepGenerator(Protocol):
    """Generate one typed agent action from a strategy-owned prompt."""

    def __call__(self, prompt: str) -> AgentStepResult: ...
