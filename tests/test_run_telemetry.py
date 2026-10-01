from dataclasses import FrozenInstanceError

import pytest

from coderepair.agent_generation import AgentStepResult
from coderepair.agent_loop import AgentRunResult
from coderepair.agent_protocol import (
    AgentObservation,
    AgentTranscriptEntry,
    FinishAction,
    ReadFileAction,
)
from coderepair.baseline import SingleShotResult
from coderepair.evaluator import EvaluationResult
from coderepair.generation import GenerationResult, GenerationUsage
from coderepair.run_telemetry import (
    RunTelemetry,
    telemetry_from_agent_run,
    telemetry_from_single_shot,
)


def evaluation(success: bool) -> EvaluationResult:
    return EvaluationResult(success, True, (), None, None, None)


def agent_step(
    usage: GenerationUsage,
    latency_seconds: float | None,
    reported_cost_usd: float | None = None,
) -> AgentStepResult:
    return AgentStepResult(
        FinishAction(), usage, latency_seconds, "fake", "model",
        reported_cost_usd=reported_cost_usd,
    )


def test_single_shot_maps_complete_raw_measurements() -> None:
    generation = GenerationResult(
        (), GenerationUsage(100, 20, 120), 0.5, "fake", "model",
        reported_cost_usd=0.0025,
    )
    result = SingleShotResult(generation, True, None, evaluation(True), 4.0)

    assert telemetry_from_single_shot(result) == RunTelemetry(
        True, 1, 0, 100, 20, 120, 0.5, 4.0, reported_cost_usd=0.0025
    )


def test_rejected_single_shot_is_unsuccessful_but_still_measured() -> None:
    generation = GenerationResult(
        (), GenerationUsage(None, 0, None), None, "fake", "model"
    )
    result = SingleShotResult(generation, False, "not writable", None, 1.25)

    assert telemetry_from_single_shot(result) == RunTelemetry(
        False, 1, 0, None, 0, None, None, 1.25
    )
    assert telemetry_from_single_shot(result).reported_cost_usd is None


def test_agent_aggregates_all_calls_and_counts_tool_errors() -> None:
    steps = (
        agent_step(GenerationUsage(100, 20, 120), 0.5),
        agent_step(GenerationUsage(50, 10, 60), 0.75),
    )
    transcript = (
        AgentTranscriptEntry(
            ReadFileAction("a.py"),
            AgentObservation("read_file", "rejected", True),
        ),
    )
    result = AgentRunResult(steps, transcript, "finish", evaluation(True), 8.0)

    assert telemetry_from_agent_run(result) == RunTelemetry(
        True, 2, 1, 150, 30, 180, 1.25, 8.0
    )


def test_missing_agent_usage_and_latency_never_become_zero() -> None:
    steps = (
        agent_step(GenerationUsage(100, 20, 120), 0.5),
        agent_step(GenerationUsage(None, 10, None), None),
    )
    result = AgentRunResult(steps, (), "finish", evaluation(False), 3.0)

    assert telemetry_from_agent_run(result) == RunTelemetry(
        False, 2, 0, None, 30, None, None, 3.0
    )


def test_optional_token_details_follow_complete_data_aggregation() -> None:
    steps = (
        agent_step(GenerationUsage(10, 4, 14, 0, 2), 0.1),
        agent_step(GenerationUsage(20, 6, 26, 3, None), 0.2),
    )
    result = AgentRunResult(steps, (), "finish", evaluation(False), 1.0)
    telemetry = telemetry_from_agent_run(result)
    assert telemetry.cached_input_tokens == 3
    assert telemetry.reasoning_output_tokens is None


def test_missing_dimension_is_independent_of_other_dimensions() -> None:
    steps = (
        agent_step(GenerationUsage(None, 20, 120), 0.5),
        agent_step(GenerationUsage(50, 10, 60), 0.75),
    )
    result = AgentRunResult(steps, (), "model_call_limit", evaluation(False), 3.0)

    telemetry = telemetry_from_agent_run(result)
    assert telemetry.input_tokens is None
    assert telemetry.output_tokens == 30
    assert telemetry.total_tokens == 180
    assert telemetry.model_latency_seconds == 1.25


def test_telemetry_is_immutable_and_accepts_zero_counts() -> None:
    telemetry = RunTelemetry(False, 0, 0, None, None, None, None, 0)
    assert telemetry.model_calls == 0
    with pytest.raises(FrozenInstanceError):
        telemetry.success = True
    with pytest.raises(AttributeError):
        telemetry.extra = 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("success", 1), ("success", None),
        ("model_calls", True), ("model_calls", -1), ("model_calls", 1.5),
        ("tool_calls", False), ("tool_calls", -1),
        ("input_tokens", True), ("input_tokens", -1),
        ("output_tokens", 1.5), ("total_tokens", "3"),
        ("model_latency_seconds", True), ("model_latency_seconds", -1),
        ("model_latency_seconds", float("nan")),
        ("model_latency_seconds", float("inf")),
        ("duration_seconds", True), ("duration_seconds", -1),
        ("duration_seconds", float("nan")),
        ("duration_seconds", float("inf")),
    ],
)
def test_rejects_invalid_telemetry_fields(field: str, value: object) -> None:
    valid = dict(
        success=True, model_calls=1, tool_calls=0,
        input_tokens=None, output_tokens=None, total_tokens=None,
        model_latency_seconds=0.5, duration_seconds=1.0,
    )
    with pytest.raises(ValueError, match=field):
        RunTelemetry(**{**valid, field: value})


def test_rejects_inconsistent_complete_token_total() -> None:
    with pytest.raises(ValueError, match="total_tokens"):
        RunTelemetry(True, 1, 0, 100, 20, 121, 0.5, 1.0)


def test_does_not_require_duration_to_exceed_model_latency() -> None:
    assert RunTelemetry(True, 1, 0, 1, 1, 2, 10.0, 0.5).duration_seconds == 0.5


def test_agent_sums_complete_reported_costs() -> None:
    steps = (
        agent_step(GenerationUsage(None, None, None), None, 0.001),
        agent_step(GenerationUsage(None, None, None), None, 0.0025),
        agent_step(GenerationUsage(None, None, None), None, 0.0005),
    )
    result = AgentRunResult(steps, (), "finish", evaluation(True), 4.0)

    assert telemetry_from_agent_run(result).reported_cost_usd == pytest.approx(0.004)


def test_missing_agent_cost_is_not_a_partial_total() -> None:
    steps = (
        agent_step(GenerationUsage(None, None, None), None, 0.002),
        agent_step(GenerationUsage(None, None, None), None, None),
    )
    result = AgentRunResult(steps, (), "finish", evaluation(False), 4.0)

    assert telemetry_from_agent_run(result).reported_cost_usd is None


def test_reported_zero_cost_is_known_not_missing() -> None:
    generation = GenerationResult(
        (), GenerationUsage(None, None, None), None, "fake", "model",
        reported_cost_usd=0.0,
    )
    single = SingleShotResult(generation, True, None, evaluation(True), 1.0)
    steps = (
        agent_step(GenerationUsage(None, None, None), None, 0.0),
        agent_step(GenerationUsage(None, None, None), None, 0.002),
    )
    agent = AgentRunResult(steps, (), "finish", evaluation(True), 2.0)

    assert telemetry_from_single_shot(single).reported_cost_usd == 0.0
    assert telemetry_from_agent_run(agent).reported_cost_usd == pytest.approx(0.002)


@pytest.mark.parametrize(
    "cost", [True, False, -0.01, float("nan"), float("inf"), "0.01"]
)
def test_telemetry_rejects_invalid_reported_cost(cost: object) -> None:
    with pytest.raises(ValueError, match="reported_cost_usd"):
        RunTelemetry(
            True, 1, 0, None, None, None, None, 1.0,
            reported_cost_usd=cost,
        )
