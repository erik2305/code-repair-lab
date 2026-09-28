from dataclasses import FrozenInstanceError, replace

import pytest

from coderepair.run_config import AgentLimits, RunConfig

RUN_CONFIG = RunConfig(
    model="example-model",
    reasoning_effort="medium",
    max_output_tokens=4096,
    request_timeout_seconds=60,
    evaluator_timeout_seconds=30,
    max_file_bytes=100_000,
    max_total_bytes=200_000,
    docker_image="coderepair-lab-sandbox:dev",
)
AGENT_LIMITS = AgentLimits(3, 12, 100_000)


def test_config_contracts_are_immutable() -> None:
    assert RUN_CONFIG.max_total_bytes >= RUN_CONFIG.max_file_bytes
    assert AGENT_LIMITS.max_model_calls == 3
    assert not hasattr(RUN_CONFIG, "__dict__")
    assert not hasattr(AGENT_LIMITS, "__dict__")
    with pytest.raises(FrozenInstanceError):
        RUN_CONFIG.model = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        AGENT_LIMITS.max_tool_calls = 4  # type: ignore[misc]


@pytest.mark.parametrize("field", ["model", "reasoning_effort", "docker_image"])
@pytest.mark.parametrize("value", ["", "   ", None, 42])
def test_run_config_rejects_invalid_strings(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        replace(RUN_CONFIG, **{field: value})


@pytest.mark.parametrize(
    "field", ["max_output_tokens", "max_file_bytes", "max_total_bytes"]
)
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "100"])
def test_run_config_rejects_invalid_integers(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        replace(RUN_CONFIG, **{field: value})


@pytest.mark.parametrize(
    "field", ["request_timeout_seconds", "evaluator_timeout_seconds"]
)
@pytest.mark.parametrize("value", [0, -1, True, float("nan"), float("inf"), "30"])
def test_run_config_rejects_invalid_timeouts(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        replace(RUN_CONFIG, **{field: value})


def test_total_context_budget_must_cover_per_file_budget() -> None:
    with pytest.raises(ValueError, match="max_total_bytes"):
        replace(RUN_CONFIG, max_total_bytes=RUN_CONFIG.max_file_bytes - 1)
    assert replace(
        RUN_CONFIG, max_total_bytes=RUN_CONFIG.max_file_bytes
    ).max_total_bytes == RUN_CONFIG.max_file_bytes


@pytest.mark.parametrize(
    "field", ["max_model_calls", "max_tool_calls", "max_transcript_bytes"]
)
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "10"])
def test_agent_limits_rejects_invalid_integers(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        replace(AGENT_LIMITS, **{field: value})
