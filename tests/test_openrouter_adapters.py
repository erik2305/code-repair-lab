"""Offline contract tests for both OpenRouter Responses adapters."""

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import BaseModel, ConfigDict

import coderepair.openrouter_agent_generator as agent_module
import coderepair.openrouter_generator as repair_module
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
from coderepair.generation import GenerationResult, GenerationUsage
from coderepair.openrouter_agent_generator import OpenRouterAgentStepGenerator
from coderepair.openrouter_generator import OpenRouterRepairGenerator
from coderepair.openrouter_response import _reported_cost, _routed_provider
from coderepair.responses_schema import _AgentStep, _RepairProposal


def _client(
    proposal: object, *, usage: object = None, model: str | None = "returned"
) -> Mock:
    client = Mock()
    client.with_options.return_value.responses.parse.return_value = SimpleNamespace(
        output_parsed=proposal,
        usage=usage,
        model=model,
    )
    return client


def _generator(kind: str, client: Mock):
    cls = (
        OpenRouterRepairGenerator if kind == "repair" else OpenRouterAgentStepGenerator
    )
    return cls(
        client,
        model="author/logical-model",
        reasoning_effort="medium",
        max_output_tokens=512,
        request_timeout_seconds=12.5,
    )


def _proposal(kind: str):
    if kind == "repair":
        return _RepairProposal.model_validate(
            {"changes": [{"path": "../outside.py", "content": "x"}]}
        )
    return _AgentStep.model_validate(
        {"action": {"type": "read_file", "path": "../outside.py"}}
    )


@pytest.mark.parametrize("kind", ["repair", "agent"])
def test_exact_request_routing_and_telemetry(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(
        _proposal(kind),
        usage=SimpleNamespace(
            input_tokens=100, output_tokens=20, total_tokens=120, cost=0.00123
        ),
    )
    response = client.with_options.return_value.responses.parse.return_value
    response.openrouter_metadata = {
        "endpoints": {
            "available": [
                {"provider": "Provider A", "selected": False},
                {"provider": "Provider B", "selected": True},
            ]
        }
    }
    clock = iter((10.0, 10.5))
    module = repair_module if kind == "repair" else agent_module
    monkeypatch.setattr(module, "perf_counter", lambda: next(clock))

    result = _generator(kind, client)("repair this")

    client.with_options.assert_called_once_with(max_retries=0, timeout=12.5)
    parse = client.with_options.return_value.responses.parse
    parse.assert_called_once_with(
        model="author/logical-model",
        reasoning={"effort": "medium"},
        input="repair this",
        text_format=_RepairProposal if kind == "repair" else _AgentStep,
        max_output_tokens=512,
        extra_body={"provider": {"allow_fallbacks": True, "require_parameters": True}},
        extra_headers={"X-OpenRouter-Metadata": "enabled"},
    )
    assert "models" not in parse.call_args.kwargs
    assert "models" not in parse.call_args.kwargs["extra_body"]
    assert result.usage == GenerationUsage(100, 20, 120)
    assert result.latency_seconds == 0.5
    assert result.provider == "openrouter"
    assert result.model == "returned"
    assert result.reported_cost_usd == 0.00123
    assert result.prompt_sha256 == sha256(b"repair this").hexdigest()
    assert result.usage.cached_input_tokens is None
    assert result.usage.reasoning_output_tokens is None
    assert result.routed_provider == "Provider B"
    if kind == "repair":
        assert result.changes == (FileChange("../outside.py", "x"),)
    else:
        assert result.action == ReadFileAction("../outside.py")


@pytest.mark.parametrize("kind", ["repair", "agent"])
def test_responses_usage_details_are_mapped_without_inference(kind: str) -> None:
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        input_tokens_details=SimpleNamespace(cached_tokens=0),
        output_tokens_details=SimpleNamespace(reasoning_tokens=7),
    )
    result = _generator(kind, _client(_proposal(kind), usage=usage))("prompt")
    assert result.usage.cached_input_tokens == 0
    assert result.usage.reasoning_output_tokens == 7
    assert result.prompt_sha256 == sha256(b"prompt").hexdigest()


@pytest.mark.parametrize("kind", ["repair", "agent"])
def test_missing_usage_metadata_model_and_cost(kind: str) -> None:
    result = _generator(kind, _client(_proposal(kind), model=None))("prompt")
    assert result.usage == GenerationUsage(None, None, None)
    assert result.reported_cost_usd is None
    assert result.routed_provider is None
    assert result.model == "author/logical-model"


@pytest.mark.parametrize("kind", ["repair", "agent"])
def test_zero_cost_from_public_pydantic_extra(kind: str) -> None:
    class ExtraUsage(BaseModel):
        model_config = ConfigDict(extra="allow")

        input_tokens: int
        output_tokens: int
        total_tokens: int

    usage = ExtraUsage.model_validate(
        {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3, "cost": 0}
    )
    client = _client(_proposal(kind), usage=usage)
    result = _generator(kind, client)("prompt")
    assert result.reported_cost_usd == 0


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {"endpoints": {}},
        {"endpoints": {"available": [{"provider": "A", "selected": False}]}},
        {
            "endpoints": {
                "available": [
                    {"provider": "A", "selected": True},
                    {"provider": "B", "selected": True},
                ]
            }
        },
        {"endpoints": {"available": [{"provider": " ", "selected": True}]}},
    ],
)
def test_missing_or_ambiguous_routing_metadata(metadata: object) -> None:
    assert _routed_provider(SimpleNamespace(openrouter_metadata=metadata)) is None


def test_routing_metadata_from_public_pydantic_extra() -> None:
    class ExtraResponse(BaseModel):
        model_config = ConfigDict(extra="allow")

        model: str

    response = ExtraResponse.model_validate(
        {
            "model": "returned",
            "openrouter_metadata": {
                "endpoints": {
                    "available": [
                        {"provider": "A", "selected": False},
                        {"provider": "B", "selected": True},
                    ]
                }
            },
        }
    )
    assert _routed_provider(response) == "B"
    assert _reported_cost(SimpleNamespace(usage={"cost": 0.0})) == 0.0


@pytest.mark.parametrize("kind", ["repair", "agent"])
def test_missing_parsed_output_and_provider_error_do_not_retry(kind: str) -> None:
    client = _client(None)
    with pytest.raises(RuntimeError, match="no parsed"):
        _generator(kind, client)("prompt")
    client.with_options.return_value.responses.parse.assert_called_once()

    client = _client(_proposal(kind))
    client.with_options.return_value.responses.parse.side_effect = RuntimeError(
        "offline"
    )
    with pytest.raises(RuntimeError, match="offline"):
        _generator(kind, client)("prompt")
    client.with_options.return_value.responses.parse.assert_called_once()


@pytest.mark.parametrize("kind", ["repair", "agent"])
@pytest.mark.parametrize(
    "field,invalid",
    [
        ("model", ""),
        ("model", " "),
        ("model", None),
        ("model", 3),
        ("reasoning_effort", ""),
        ("reasoning_effort", " "),
        ("reasoning_effort", None),
        ("reasoning_effort", 3),
        ("max_output_tokens", True),
        ("max_output_tokens", 0),
        ("max_output_tokens", -1),
        ("max_output_tokens", 1.5),
        ("max_output_tokens", "5"),
        ("request_timeout_seconds", float("inf")),
        ("request_timeout_seconds", float("nan")),
        ("request_timeout_seconds", 0),
        ("request_timeout_seconds", -1),
        ("request_timeout_seconds", True),
        ("request_timeout_seconds", "1"),
    ],
)
def test_constructor_validation(kind: str, field: str, invalid: object) -> None:
    cls = (
        OpenRouterRepairGenerator if kind == "repair" else OpenRouterAgentStepGenerator
    )
    kwargs = dict(
        model="m",
        reasoning_effort="medium",
        max_output_tokens=5,
        request_timeout_seconds=1,
    )
    kwargs[field] = invalid
    with pytest.raises(ValueError, match=field):
        cls(Mock(), **kwargs)


@pytest.mark.parametrize("kind", ["repair", "agent"])
@pytest.mark.parametrize("prompt", ["", " ", None, 7])
def test_prompt_validation_before_request(kind: str, prompt: object) -> None:
    client = _client(_proposal(kind))
    with pytest.raises(ValueError, match="prompt"):
        _generator(kind, client)(prompt)
    client.with_options.assert_not_called()


@pytest.mark.parametrize(
    "action,expected",
    [
        ({"type": "read_file", "path": "a.py"}, ReadFileAction("a.py")),
        ({"type": "run_reproduction"}, RunReproductionAction()),
        ({"type": "run_full_tests"}, RunFullTestsAction()),
        ({"type": "run_lint"}, RunLintAction()),
        ({"type": "finish"}, FinishAction()),
        (
            {
                "type": "apply_file_changes",
                "changes": [{"path": "a.py", "content": "x"}],
            },
            ApplyFileChangesAction((FileChange("a.py", "x"),)),
        ),
    ],
)
def test_agent_maps_all_six_actions(action: dict, expected: object) -> None:
    proposal = _AgentStep.model_validate({"action": action})
    assert _generator("agent", _client(proposal))("prompt").action == expected


def test_empty_repair_proposal() -> None:
    proposal = _RepairProposal.model_validate({"changes": []})
    assert _generator("repair", _client(proposal))("prompt").changes == ()


@pytest.mark.parametrize(
    "result",
    [
        GenerationResult((), GenerationUsage(None, None, None), None, None, None),
        AgentStepResult(
            FinishAction(), GenerationUsage(None, None, None), None, None, None
        ),
    ],
)
def test_domain_result_validates_optional_routed_provider(result: object) -> None:
    assert result.routed_provider is None
    assert replace(result, routed_provider="Provider B").routed_provider == "Provider B"
    for invalid in ("", " ", 123):
        with pytest.raises(ValueError, match="routed_provider"):
            replace(result, routed_provider=invalid)
