"""Manual OpenRouter single-shot smoke test for dev-001 (not run by pytest)."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from openai import OpenAI

from coderepair.baseline import SingleShotResult, run_single_shot_baseline
from coderepair.openrouter_generator import OpenRouterRepairGenerator
from coderepair.path_policy import validate_workspace_path
from coderepair.run_config import RunConfig
from coderepair.workspace import create_workspace, destroy_workspace

TASK_MANIFEST = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "dev" / "dev-001" / "task.yaml"
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _print_report(result: SingleShotResult, config: RunConfig) -> None:
    generation = result.generation
    evaluation = result.evaluation
    print("task: dev-001")
    print(f"gateway/provider: {generation.provider}")
    print(f"requested model: {config.model}")
    print(f"returned model: {generation.model}")
    print(f"routed provider: {generation.routed_provider}")
    print(f"reasoning effort: {config.reasoning_effort}")
    print("cross-model fallback: disabled")
    print("same-model provider fallback: enabled")
    print("require parameters: enabled")
    print(f"input tokens: {generation.usage.input_tokens}")
    print(f"output tokens: {generation.usage.output_tokens}")
    print(f"total tokens: {generation.usage.total_tokens}")
    print(f"reported cost USD: {generation.reported_cost_usd}")
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
        print(f"reproduction exit code: {evaluation.reproduction.exit_code}")
        print(f"full-test exit code: {evaluation.full_test.exit_code}")
        lint_exit = (
            "not configured" if evaluation.lint is None else evaluation.lint.exit_code
        )
        print(f"lint exit code: {lint_exit}")


def main() -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required")
    model = os.environ.get("OPENROUTER_MODEL")
    if not model or not model.strip():
        raise RuntimeError("OPENROUTER_MODEL is required")
    config = RunConfig(
        model=model,
        reasoning_effort="medium",
        max_output_tokens=4096,
        request_timeout_seconds=60,
        evaluator_timeout_seconds=30,
        max_file_bytes=100_000,
        max_total_bytes=200_000,
        docker_image="coderepair-lab-sandbox:dev",
    )
    with TemporaryDirectory(prefix="coderepair-openrouter-dev001-") as temporary:
        workspace = create_workspace(TASK_MANIFEST, Path(temporary) / "workspace")
        try:
            generator = OpenRouterRepairGenerator(
                OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key),
                model=config.model,
                reasoning_effort=config.reasoning_effort,
                max_output_tokens=config.max_output_tokens,
                request_timeout_seconds=config.request_timeout_seconds,
            )
            result = run_single_shot_baseline(
                TASK_MANIFEST, workspace, generator=generator, config=config
            )
        finally:
            destroy_workspace(workspace)
    _print_report(result, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
