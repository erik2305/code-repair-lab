"""Manual, single-request Gemini smoke test for the dev-001 baseline."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict

from coderepair.baseline import SingleShotResult, run_single_shot_baseline
from coderepair.file_changes import FileChange
from coderepair.generation import GenerationResult, GenerationUsage
from coderepair.path_policy import validate_workspace_path
from coderepair.run_config import RunConfig
from coderepair.workspace import create_workspace, destroy_workspace

CONFIG = RunConfig(
    model="gemini-3.8-flash",
    reasoning_effort="medium",
    max_output_tokens=4096,
    request_timeout_seconds=60,
    evaluator_timeout_seconds=30,
    max_file_bytes=100_000,
    max_total_bytes=200_000,
    docker_image="coderepair-lab-sandbox:dev",
)

TASK_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "dev"
    / "dev-001"
    / "task.yaml"
)


class _GeminiFileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str


class _GeminiRepairProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: list[_GeminiFileChange]


class GeminiRepairGenerator:
    """Turn one Gemini Interactions API request into one repair proposal."""

    def __init__(
        self,
        client: genai.Client,
        *,
        model: str,
        thinking_level: str,
        max_output_tokens: int,
    ) -> None:
        self._client = client
        self._model = model
        self._thinking_level = thinking_level
        self._max_output_tokens = max_output_tokens

    def __call__(self, prompt: str) -> GenerationResult:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        started_at = perf_counter()

        interaction = self._client.interactions.create(
            model=self._model,
            input=prompt,
            generation_config={
                "thinking_level": self._thinking_level,
                "max_output_tokens": self._max_output_tokens,
            },
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": _GeminiRepairProposal.model_json_schema(),
            },
            store=False,
        )

        latency_seconds = perf_counter() - started_at

        if not interaction.output_text:
            raise RuntimeError("Gemini response has no output text")

        proposal = _GeminiRepairProposal.model_validate_json(
            interaction.output_text
        )

        changes = tuple(
            FileChange(
                path=change.path,
                content=change.content,
            )
            for change in proposal.changes
        )

        usage = interaction.usage

        if usage is None:
            generation_usage = GenerationUsage(
                None,
                None,
                None,
            )
        else:
            input_tokens = usage.total_input_tokens
            total_tokens = usage.total_tokens

            # GenerationUsage requires:
            # total_tokens == input_tokens + output_tokens.
            #
            # Gemini reports visible output and thinking separately, while
            # total_tokens also includes internal/thought tokens. For the
            # provider-neutral abstraction, treat every non-input token as
            # output usage.
            output_tokens = (
                None
                if input_tokens is None or total_tokens is None
                else total_tokens - input_tokens
            )

            generation_usage = GenerationUsage(
                input_tokens,
                output_tokens,
                total_tokens,
            )

        return GenerationResult(
            changes=changes,
            usage=generation_usage,
            latency_seconds=latency_seconds,
            provider="google",
            model=interaction.model or self._model,
        )


def _print_report(result: SingleShotResult) -> None:
    generation = result.generation
    evaluation = result.evaluation

    print("task: dev-001")
    print(f"provider: {generation.provider}")
    print(f"requested model: {CONFIG.model}")
    print(f"returned model: {generation.model}")
    print(f"thinking level: {CONFIG.reasoning_effort}")
    print(f"input tokens: {generation.usage.input_tokens}")
    print(f"output tokens: {generation.usage.output_tokens}")
    print(f"total tokens: {generation.usage.total_tokens}")
    print(f"request latency (seconds): {generation.latency_seconds}")
    print(f"proposed file changes: {len(result.changes)}")

    print("proposed relative paths:")
    for change in result.changes:
        try:
            path = validate_workspace_path(change.path)
        except ValueError:
            path = "<invalid path>"
        print(f"  - {path}")

    print(f"mutation applied: {result.mutation_applied}")

    if result.mutation_error is not None:
        print(f"mutation error: {result.mutation_error}")

    if evaluation is None:
        print("overall evaluation success: not run")
        print("reproduction exit code: not run")
        print("full-test exit code: not run")
        print("lint exit code: not run")
    else:
        print(f"overall evaluation success: {evaluation.success}")
        print(
            f"reproduction exit code: "
            f"{evaluation.reproduction.exit_code}"
        )
        print(
            f"full-test exit code: "
            f"{evaluation.full_test.exit_code}"
        )

        lint_exit = (
            "not configured"
            if evaluation.lint is None
            else evaluation.lint.exit_code
        )
        print(f"lint exit code: {lint_exit}")


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=CONFIG.request_timeout_seconds * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=1,
            ),
        ),
    )

    try:
        with TemporaryDirectory(
            prefix="coderepair-dev001-"
        ) as temporary_directory:
            destination = Path(temporary_directory) / "workspace"
            workspace = create_workspace(
                TASK_MANIFEST,
                destination,
            )

            try:
                generator = GeminiRepairGenerator(
                    client,
                    model=CONFIG.model,
                    thinking_level=CONFIG.reasoning_effort,
                    max_output_tokens=CONFIG.max_output_tokens,
                )

                result = run_single_shot_baseline(
                    TASK_MANIFEST,
                    workspace,
                    generator=generator,
                    config=CONFIG,
                )
            finally:
                destroy_workspace(workspace)
    finally:
        client.close()

    _print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
