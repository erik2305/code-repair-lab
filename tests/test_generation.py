from dataclasses import replace

import pytest

from coderepair.file_changes import FileChange
from coderepair.generation import GenerationResult, GenerationUsage


@pytest.mark.parametrize(
    "field",
    [
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cached_input_tokens",
        "reasoning_output_tokens",
    ],
)
@pytest.mark.parametrize("value", [-1, True, 1.5, "3"])
def test_rejects_invalid_token_count(field: str, value: object) -> None:
    values = {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    values[field] = value

    with pytest.raises(ValueError, match=field):
        GenerationUsage(**values)  # type: ignore[arg-type]


def test_total_tokens_must_equal_input_plus_output() -> None:
    with pytest.raises(ValueError, match="total_tokens"):
        GenerationUsage(100, 20, 119)

    assert GenerationUsage(100, 20, 120).total_tokens == 120
    assert GenerationUsage(None, None, None).total_tokens is None
    assert GenerationUsage(100, 20, 120, 0, 3).cached_input_tokens == 0


@pytest.mark.parametrize("value", ["", "A" * 64, "g" * 64, 3])
def test_prompt_digest_must_be_lowercase_sha256(value: object) -> None:
    with pytest.raises(ValueError, match="prompt_sha256"):
        GenerationResult(
            (),
            GenerationUsage(None, None, None),
            None,
            None,
            None,
            prompt_sha256=value,
        )


@pytest.mark.parametrize("latency", [-0.1, True, float("inf"), float("nan"), "1"])
def test_rejects_invalid_latency(latency: object) -> None:
    with pytest.raises(ValueError, match="latency_seconds"):
        GenerationResult((), GenerationUsage(None, None, None), latency, None, None)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["provider", "model"])
@pytest.mark.parametrize("value", ["", "   ", 5])
def test_rejects_invalid_provider_or_model(field: str, value: object) -> None:
    result = GenerationResult((), GenerationUsage(None, None, None), None, None, None)

    with pytest.raises(ValueError, match=field):
        replace(result, **{field: value})


def test_generation_requires_immutable_file_changes_and_usage() -> None:
    usage = GenerationUsage(100, 20, 120)
    change = FileChange("text_utils.py", "replacement")
    result = GenerationResult((change,), usage, 0.5, "fake", "fake-model")

    assert result.changes == (change,)
    assert result.usage is usage
    with pytest.raises(ValueError, match="changes"):
        GenerationResult([change], usage, 0.5, "fake", "fake-model")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="changes"):
        GenerationResult(({"path": "text_utils.py"},), usage, 0.5, "fake", "fake-model")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="usage"):
        GenerationResult((change,), None, 0.5, "fake", "fake-model")  # type: ignore[arg-type]


@pytest.mark.parametrize("cost", [None, 0, 0.0, 0.0015])
def test_generation_accepts_optional_reported_cost(cost: float | None) -> None:
    result = GenerationResult(
        (),
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
def test_generation_rejects_invalid_reported_cost(cost: object) -> None:
    with pytest.raises(ValueError, match="reported_cost_usd"):
        GenerationResult(
            (),
            GenerationUsage(None, None, None),
            None,
            None,
            None,
            reported_cost_usd=cost,
        )
