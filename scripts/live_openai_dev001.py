"""Manual, single-request OpenAI smoke test for the dev-001 baseline."""

from pathlib import Path
from tempfile import TemporaryDirectory

from openai import OpenAI

from coderepair.baseline import SingleShotResult, run_single_shot_baseline
from coderepair.openai_generator import OpenAIRepairGenerator
from coderepair.path_policy import validate_workspace_path
from coderepair.run_config import RunConfig
from coderepair.workspace import create_workspace, destroy_workspace

CONFIG = RunConfig(
    model="gpt-6-luna",
    reasoning_effort="medium",
    max_output_tokens=4096,
    request_timeout_seconds=60,
    evaluator_timeout_seconds=30,
    max_file_bytes=100_000,
    max_total_bytes=200_000,
    docker_image="coderepair-lab-sandbox:dev",
)

TASK_MANIFEST = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "dev" / "dev-001" / "task.yaml"
)


def _print_report(result: SingleShotResult) -> None:
    generation = result.generation
    evaluation = result.evaluation
    print("task: dev-001")
    print(f"provider: {generation.provider}")
    print(f"requested model: {CONFIG.model}")
    print(f"returned model: {generation.model}")
    print(f"reasoning effort: {CONFIG.reasoning_effort}")
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
        print(f"reproduction exit code: {evaluation.reproduction.exit_code}")
        print(f"full-test exit code: {evaluation.full_test.exit_code}")
        lint_exit = (
            "not configured" if evaluation.lint is None else evaluation.lint.exit_code
        )
        print(f"lint exit code: {lint_exit}")


def main() -> int:
    with TemporaryDirectory(prefix="coderepair-dev001-") as temporary_directory:
        destination = Path(temporary_directory) / "workspace"
        workspace = create_workspace(TASK_MANIFEST, destination)
        try:
            generator = OpenAIRepairGenerator(
                OpenAI(),
                model=CONFIG.model,
                reasoning_effort=CONFIG.reasoning_effort,
                max_output_tokens=CONFIG.max_output_tokens,
                request_timeout_seconds=CONFIG.request_timeout_seconds,
            )
            result = run_single_shot_baseline(
                TASK_MANIFEST,
                workspace,
                generator=generator,
                config=CONFIG,
            )
        finally:
            destroy_workspace(workspace)

    _print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
