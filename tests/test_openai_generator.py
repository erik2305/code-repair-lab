from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

import coderepair.openai_generator as openai_generator
from coderepair.file_changes import FileChange
from coderepair.generation import GenerationUsage
from coderepair.openai_generator import (
    OpenAIRepairGenerator,
    _OpenAIRepairProposal,
)


def fake_client(
    *,
    changes: list[dict[str, str]] | None = None,
    usage: object = None,
    model: str | None = "returned-model",
    parsed: bool = True,
) -> Mock:
    client = Mock()
    client.with_options.return_value.responses.parse.return_value = SimpleNamespace(
        output_parsed=(
            _OpenAIRepairProposal.model_validate({"changes": changes or []})
            if parsed
            else None
        ),
        usage=usage,
        model=model,
    )
    return client


def generator(client: Mock) -> OpenAIRepairGenerator:
    return OpenAIRepairGenerator(
        client,
        model="requested-model",
        reasoning_effort="medium",
        max_output_tokens=512,
        request_timeout_seconds=12.5,
    )


def test_exact_single_request_changes_usage_model_and_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = fake_client(
        changes=[
            {"path": "src/a.py", "content": "first\n"},
            {"path": "src/b.py", "content": "second\n"},
        ],
        usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
    )
    times = iter((10.0, 10.5))
    monkeypatch.setattr(openai_generator, "perf_counter", lambda: next(times))

    result = generator(client)("repair this")

    client.with_options.assert_called_once_with(max_retries=0, timeout=12.5)
    parse = client.with_options.return_value.responses.parse
    parse.assert_called_once_with(
        model="requested-model",
        reasoning={"effort": "medium"},
        input="repair this",
        text_format=_OpenAIRepairProposal,
        max_output_tokens=512,
    )
    assert result.changes == (
        FileChange("src/a.py", "first\n"),
        FileChange("src/b.py", "second\n"),
    )
    assert result.usage == GenerationUsage(100, 20, 120)
    assert result.latency_seconds == 0.5
    assert result.provider == "openai"
    assert result.model == "returned-model"


def test_missing_usage_and_model_fallback() -> None:
    client = fake_client(usage=None, model=None)

    result = generator(client)("repair this")

    assert result.usage == GenerationUsage(None, None, None)
    assert result.model == "requested-model"
    assert result.changes == ()


def test_empty_structured_proposal_is_valid() -> None:
    result = generator(fake_client(changes=[]))("repair this")

    assert result.changes == ()


def test_missing_parsed_output_raises_without_retry() -> None:
    client = fake_client(parsed=False)

    with pytest.raises(RuntimeError, match="no parsed repair proposal"):
        generator(client)("repair this")

    client.with_options.assert_called_once_with(max_retries=0, timeout=12.5)
    client.with_options.return_value.responses.parse.assert_called_once()


def test_provider_failure_propagates_after_one_attempt() -> None:
    client = fake_client()
    client.with_options.return_value.responses.parse.side_effect = RuntimeError(
        "provider unavailable"
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        generator(client)("repair this")

    client.with_options.assert_called_once_with(max_retries=0, timeout=12.5)
    client.with_options.return_value.responses.parse.assert_called_once()


def test_structured_schema_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        _OpenAIRepairProposal.model_validate({"changes": [], "usage": 100})
    with pytest.raises(ValidationError):
        _OpenAIRepairProposal.model_validate(
            {"changes": [{"path": "a.py", "content": "x", "explanation": "extra"}]}
        )


@pytest.mark.parametrize("model", ["", "   ", None, 3])
def test_rejects_invalid_model(model: object) -> None:
    with pytest.raises(ValueError, match="model"):
        OpenAIRepairGenerator(
            Mock(),
            model=model,
            reasoning_effort="medium",
            max_output_tokens=512,
            request_timeout_seconds=12.5,
        )  # type: ignore[arg-type]


@pytest.mark.parametrize("reasoning_effort", ["", "   ", None, 3])
def test_rejects_invalid_reasoning_effort(reasoning_effort: object) -> None:
    with pytest.raises(ValueError, match="reasoning_effort"):
        OpenAIRepairGenerator(
            Mock(),
            model="requested-model",
            reasoning_effort=reasoning_effort,
            max_output_tokens=512,
            request_timeout_seconds=12.5,
        )  # type: ignore[arg-type]


@pytest.mark.parametrize("max_output_tokens", [0, -1, True, 1.5, "512"])
def test_rejects_invalid_output_budget(max_output_tokens: object) -> None:
    with pytest.raises(ValueError, match="max_output_tokens"):
        OpenAIRepairGenerator(
            Mock(),
            model="requested-model",
            reasoning_effort="medium",
            max_output_tokens=max_output_tokens,
            request_timeout_seconds=12.5,
        )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "timeout", [0, -1, True, float("inf"), float("nan"), "12.5"]
)
def test_rejects_invalid_timeout(timeout: object) -> None:
    with pytest.raises(ValueError, match="request_timeout_seconds"):
        OpenAIRepairGenerator(
            Mock(),
            model="requested-model",
            reasoning_effort="medium",
            max_output_tokens=512,
            request_timeout_seconds=timeout,
        )  # type: ignore[arg-type]


@pytest.mark.parametrize("prompt", ["", "   ", None, 7])
def test_rejects_invalid_prompt_without_request(prompt: object) -> None:
    client = fake_client()

    with pytest.raises(ValueError, match="prompt"):
        generator(client)(prompt)  # type: ignore[arg-type]

    client.with_options.assert_not_called()
