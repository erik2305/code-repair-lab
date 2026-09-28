"""Provider-neutral agent-step result validation."""

from dataclasses import FrozenInstanceError

import pytest

from coderepair.agent_generation import AgentStepResult
from coderepair.agent_protocol import (
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
)
from coderepair.generation import GenerationUsage


def test_agent_step_result_is_immutable_and_validated() -> None:
    valid = dict(
        action=FinishAction(),
        usage=GenerationUsage(1, 2, 3),
        latency_seconds=0.5,
        provider="openrouter",
        model="model",
    )
    result = AgentStepResult(**valid)
    for action in (
        ReadFileAction("a.py"),
        ApplyFileChangesAction(()),
        RunReproductionAction(),
        RunFullTestsAction(),
        RunLintAction(),
        FinishAction(),
    ):
        assert AgentStepResult(**{**valid, "action": action}).action == action
    with pytest.raises(FrozenInstanceError):
        result.model = "other"
    with pytest.raises(AttributeError):
        result.extra = 1
    for field, value in (
        ("action", object()),
        ("usage", object()),
        ("latency_seconds", -1),
        ("latency_seconds", True),
        ("latency_seconds", float("nan")),
        ("latency_seconds", float("inf")),
        ("provider", " "),
        ("model", ""),
    ):
        with pytest.raises(ValueError, match=field):
            AgentStepResult(**{**valid, field: value})


@pytest.mark.parametrize("cost", [None, 0, 0.0, 0.0015])
def test_agent_step_accepts_optional_reported_cost(cost: float | None) -> None:
    result = AgentStepResult(
        FinishAction(),
        GenerationUsage(None, None, None),
        None,
        None,
        None,
        reported_cost_usd=cost,
    )
    assert result.reported_cost_usd == cost


@pytest.mark.parametrize(
    "cost", [True, False, -0.01, float("nan"), float("inf"), "0.01"]
)
def test_agent_step_rejects_invalid_reported_cost(cost: object) -> None:
    with pytest.raises(ValueError, match="reported_cost_usd"):
        AgentStepResult(
            FinishAction(),
            GenerationUsage(None, None, None),
            None,
            None,
            None,
            reported_cost_usd=cost,
        )
