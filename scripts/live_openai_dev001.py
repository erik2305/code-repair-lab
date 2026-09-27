"""Manual, single-request OpenAI smoke test for the dev-001 baseline."""

from pathlib import Path
from tempfile import TemporaryDirectory

from openai import OpenAI

from coderepair.baseline import SingleShotResult, run_single_shot_baseline
from coderepair.openai_generator import OpenAIRepairGenerator
from coderepair.path_policy import validate_workspace_path
from coderepair.workspace import create_workspace, destroy_workspace

MODEL = "gpt-6-luna"
REASONING_EFFORT = "medium"
MAX_OUTPUT_TOKENS = 4096
REQUEST_TIMEOUT_SECONDS = 60
SANDBOX_IMAGE = "coderepair-lab-sandbox:dev"
EVALUATOR_TIMEOUT_SECONDS = 30
MAX_FILE_BYTES = 100_000
MAX_TOTAL_BYTES = 200_000

TASK_MANIFEST = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "dev" / "dev-001" / "task.yaml"
)


def _print_report(result: SingleShotResult) -> None:
    generation = result.generation
    evaluation = result.evaluation
    print("task: dev-001")
    print(f"provider: {generation.provider}")
    print(f"requested model: {MODEL}")
    print(f"returned model: {generation.model}")
    print(f"reasoning effort: {REASONING_EFFORT}")
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
                model=MODEL,
                reasoning_effort=REASONING_EFFORT,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            )
            result = run_single_shot_baseline(
                TASK_MANIFEST,
                workspace,
                generator=generator,
                max_file_bytes=MAX_FILE_BYTES,
                max_total_bytes=MAX_TOTAL_BYTES,
                image=SANDBOX_IMAGE,
                timeout_seconds=EVALUATOR_TIMEOUT_SECONDS,
            )
        finally:
            destroy_workspace(workspace)

    _print_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
