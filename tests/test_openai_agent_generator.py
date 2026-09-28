from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

import coderepair.openai_agent_generator as adapter
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
from coderepair.openai_agent_generator import (
    OpenAIAgentStepGenerator,
    _OpenAIAgentStep,
)


def fake_client(
    action: dict[str, object] | None = None,
    *,
    usage: object = None,
    model: str | None = "returned-model",
    parsed: bool = True,
) -> Mock:
    client = Mock()
    client.with_options.return_value.responses.parse.return_value = SimpleNamespace(
        output_parsed=(
            _OpenAIAgentStep.model_validate({"action": action or {"type": "finish"}})
            if parsed
            else None
        ),
        usage=usage,
        model=model,
    )
    return client


def generator(client: Mock) -> OpenAIAgentStepGenerator:
    return OpenAIAgentStepGenerator(
        client,
        model="requested-model",
        reasoning_effort="medium",
        max_output_tokens=512,
        request_timeout_seconds=12.5,
    )


def test_exact_single_request_and_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    client = fake_client(
        {"type": "read_file", "path": "../outside.py"},
        usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
    )
    times = iter((10.0, 10.5))
    monkeypatch.setattr(adapter, "perf_counter", lambda: next(times))

    result = generator(client)("choose one action")

    client.with_options.assert_called_once_with(max_retries=0, timeout=12.5)
    client.with_options.return_value.responses.parse.assert_called_once_with(
        model="requested-model",
        reasoning={"effort": "medium"},
        input="choose one action",
        text_format=_OpenAIAgentStep,
        max_output_tokens=512,
    )
    assert result.action == ReadFileAction("../outside.py")
    assert result.usage == GenerationUsage(100, 20, 120)
    assert result.latency_seconds == 0.5
    assert result.provider == "openai"
    assert result.model == "returned-model"
    assert result.reported_cost_usd is None


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ({"type": "read_file", "path": "src/a.py"}, ReadFileAction("src/a.py")),
        ({"type": "run_reproduction"}, RunReproductionAction()),
        ({"type": "run_full_tests"}, RunFullTestsAction()),
        ({"type": "run_lint"}, RunLintAction()),
        ({"type": "finish"}, FinishAction()),
    ],
)
def test_maps_each_simple_action(
    action: dict[str, object], expected: object
) -> None:
    assert generator(fake_client(action))("next").action == expected


def test_maps_ordered_file_changes_without_policy_validation() -> None:
    action = {
        "type": "apply_file_changes",
        "changes": [
            {"path": "src/a.py", "content": "first\n"},
            {"path": "../outside.py", "content": "second\n"},
        ],
    }

    result = generator(fake_client(action))("next")

    assert result.action == ApplyFileChangesAction(
        (FileChange("src/a.py", "first\n"), FileChange("../outside.py", "second\n"))
    )


def test_missing_usage_and_model_fallback() -> None:
    result = generator(fake_client(model=None))("next")

    assert result.usage == GenerationUsage(None, None, None)
    assert result.model == "requested-model"


def test_schema_has_object_root_and_strict_nested_variants() -> None:
    schema = _OpenAIAgentStep.model_json_schema()
    assert schema["type"] == "object"
    assert "anyOf" not in schema
    assert schema["additionalProperties"] is False
    assert len(schema["properties"]["action"]["anyOf"]) == 6
    assert all(
        item["additionalProperties"] is False for item in schema["$defs"].values()
    )

    for malformed in (
        {"action": {"type": "finish"}, "usage": 100},
        {"action": {"type": "finish", "success": True}},
        {"action": {"type": "read_file", "path": "a.py", "argv": []}},
        {"action": {"type": "apply_file_changes", "changes": [
            {"path": "a.py", "content": "x", "extra": "no"}
        ]}},
        {"action": {"type": "run_command", "argv": ["echo"]}},
    ):
        with pytest.raises(ValidationError):
            _OpenAIAgentStep.model_validate(malformed)


def test_unexpected_parsed_action_fails_clearly() -> None:
    client = fake_client()
    response = client.with_options.return_value.responses.parse.return_value
    response.output_parsed = SimpleNamespace(action=object())

    with pytest.raises(RuntimeError, match="unsupported parsed agent action"):
        generator(client)("next")

    client.with_options.return_value.responses.parse.assert_called_once()


def test_missing_parsed_output_raises_without_retry() -> None:
    client = fake_client(parsed=False)

    with pytest.raises(RuntimeError, match="no parsed agent action"):
        generator(client)("next")

    client.with_options.assert_called_once_with(max_retries=0, timeout=12.5)
    client.with_options.return_value.responses.parse.assert_called_once()


def test_provider_failure_propagates_after_one_request() -> None:
    client = fake_client()
    client.with_options.return_value.responses.parse.side_effect = RuntimeError(
        "provider unavailable"
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        generator(client)("next")

    client.with_options.assert_called_once_with(max_retries=0, timeout=12.5)
    client.with_options.return_value.responses.parse.assert_called_once()


@pytest.mark.parametrize("field", ["model", "reasoning_effort"])
@pytest.mark.parametrize("value", ["", "   ", None, 3])
def test_rejects_invalid_identity_fields(field: str, value: object) -> None:
    kwargs = dict(model="requested-model", reasoning_effort="medium")
    kwargs[field] = value
    with pytest.raises(ValueError, match=field):
        OpenAIAgentStepGenerator(
            Mock(), **kwargs, max_output_tokens=512, request_timeout_seconds=12.5
        )


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "512"])
def test_rejects_invalid_output_budget(value: object) -> None:
    with pytest.raises(ValueError, match="max_output_tokens"):
        OpenAIAgentStepGenerator(
            Mock(), model="m", reasoning_effort="medium",
            max_output_tokens=value, request_timeout_seconds=12.5,
        )


@pytest.mark.parametrize("value", [0, -1, True, float("inf"), float("nan"), "12.5"])
def test_rejects_invalid_timeout(value: object) -> None:
    with pytest.raises(ValueError, match="request_timeout_seconds"):
        OpenAIAgentStepGenerator(
            Mock(), model="m", reasoning_effort="medium",
            max_output_tokens=512, request_timeout_seconds=value,
        )


@pytest.mark.parametrize("prompt", ["", "   ", None, 7])
def test_rejects_invalid_prompt_before_request(prompt: object) -> None:
    client = fake_client()
    with pytest.raises(ValueError, match="prompt"):
        generator(client)(prompt)
    client.with_options.assert_not_called()


def test_agent_step_result_is_immutable_and_validated() -> None:
    valid = dict(
        action=FinishAction(), usage=GenerationUsage(1, 2, 3),
        latency_seconds=0.5, provider="openai", model="model",
    )
    result = AgentStepResult(**valid)
    for action in (
        ReadFileAction("a.py"), ApplyFileChangesAction(()),
        RunReproductionAction(), RunFullTestsAction(), RunLintAction(), FinishAction(),
    ):
        assert AgentStepResult(**{**valid, "action": action}).action == action
    with pytest.raises(FrozenInstanceError):
        result.model = "other"
    with pytest.raises(AttributeError):
        result.extra = 1

    for field, value in (
        ("action", object()), ("usage", object()),
        ("latency_seconds", -1), ("latency_seconds", True),
        ("latency_seconds", float("nan")), ("latency_seconds", float("inf")),
        ("provider", " "), ("model", ""),
    ):
        with pytest.raises(ValueError, match=field):
            AgentStepResult(**{**valid, field: value})


@pytest.mark.parametrize("cost", [None, 0, 0.0, 0.0015])
def test_agent_step_accepts_optional_reported_cost(cost: float | None) -> None:
    result = AgentStepResult(
        FinishAction(), GenerationUsage(None, None, None), None, None, None,
        reported_cost_usd=cost,
    )
    assert result.reported_cost_usd == cost


@pytest.mark.parametrize(
    "cost", [True, False, -0.01, float("nan"), float("inf"), "0.01"]
)
def test_agent_step_rejects_invalid_reported_cost(cost: object) -> None:
    with pytest.raises(ValueError, match="reported_cost_usd"):
        AgentStepResult(
            FinishAction(), GenerationUsage(None, None, None), None, None, None,
            reported_cost_usd=cost,
        )
