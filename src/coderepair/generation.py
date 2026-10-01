"""Provider-neutral repair generation output and basic telemetry."""

import math
from dataclasses import dataclass

from coderepair.file_changes import FileChange


@dataclass(frozen=True, slots=True)
class GenerationUsage:
    """Common token counts reported by a repair generator."""

    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cached_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "reasoning_output_tokens",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or None")
        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens must equal input_tokens + output_tokens")


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """One immutable file-change proposal with provider-neutral metadata."""

    changes: tuple[FileChange, ...]
    usage: GenerationUsage
    latency_seconds: float | None
    provider: str | None
    model: str | None
    reported_cost_usd: float | None = None
    routed_provider: str | None = None
    prompt_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.changes, tuple) or any(
            not isinstance(change, FileChange) for change in self.changes
        ):
            raise ValueError("changes must be a tuple of FileChange objects")
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
        for name in ("provider", "model", "routed_provider"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")
        if self.prompt_sha256 is not None and (
            not isinstance(self.prompt_sha256, str)
            or len(self.prompt_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.prompt_sha256)
        ):
            raise ValueError("prompt_sha256 must be a lowercase SHA-256 hex digest")
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
