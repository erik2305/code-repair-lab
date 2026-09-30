"""Manual paired DEV experiment; never run from the automated test suite."""

import argparse
import json
import os
import platform
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv
from openai import OpenAI

from coderepair.agent_loop import run_agentic_repair
from coderepair.baseline import run_single_shot_baseline
from coderepair.experiment import (
    ExperimentProvenance,
    agent_record,
    baseline_record,
    counterbalanced_order,
    inspect_docker_image,
    open_new_output,
    require_clean_git,
)
from coderepair.openrouter_agent_generator import OpenRouterAgentStepGenerator
from coderepair.openrouter_generator import OpenRouterRepairGenerator
from coderepair.run_config import AgentLimits, RunConfig
from coderepair.run_telemetry import (
    telemetry_from_agent_run,
    telemetry_from_single_shot,
)
from coderepair.workspace import create_workspace, destroy_workspace

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_IDS = ("dev-001", "dev-002", "dev-003", "dev-004")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_OUTPUT_TOKENS = 4096
REQUEST_TIMEOUT_SECONDS = 60
EVALUATOR_TIMEOUT_SECONDS = 30
MAX_FILE_BYTES = 100_000
MAX_TOTAL_BYTES = 200_000
DOCKER_IMAGE = "coderepair-lab-sandbox:dev"
AGENT_LIMITS = AgentLimits(
    max_model_calls=6,
    max_tool_calls=5,
    max_transcript_bytes=100_000,
)


def _positive_repetitions(value: str) -> int:
    try:
        repetitions = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "repetitions must be a positive integer"
        ) from error
    if repetitions <= 0:
        raise argparse.ArgumentTypeError("repetitions must be a positive integer")
    return repetitions


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run paired DEV repair attempts")
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--repetitions", type=_positive_repetitions, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    config = RunConfig(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        evaluator_timeout_seconds=EVALUATOR_TIMEOUT_SECONDS,
        max_file_bytes=MAX_FILE_BYTES,
        max_total_bytes=MAX_TOTAL_BYTES,
        docker_image=DOCKER_IMAGE,
    )
    if args.output.exists():
        raise ValueError("output file already exists")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required")

    git_commit = require_clean_git(PROJECT_ROOT)
    image_id, image_digests = inspect_docker_image(config.docker_image)
    provenance = ExperimentProvenance(
        experiment_id=datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"),
        git_commit=git_commit,
        docker_image_id=image_id,
        docker_repo_digests=image_digests,
        python_version=platform.python_version(),
        platform=platform.platform(),
    )

    completed = 0
    with open_new_output(args.output) as output:
        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
        try:
            for task_index, task_id in enumerate(TASK_IDS):
                task_manifest = (
                    PROJECT_ROOT / "benchmarks" / "dev" / task_id / "task.yaml"
                )
                for repetition in range(1, args.repetitions + 1):
                    order = counterbalanced_order(task_index, repetition)
                    for position, strategy in enumerate(order, start=1):
                        started_utc = _utc_now()
                        with TemporaryDirectory(prefix="coderepair-dev-") as temporary:
                            workspace = create_workspace(
                                task_manifest, Path(temporary) / "workspace"
                            )
                            try:
                                if strategy == "baseline":
                                    generator = OpenRouterRepairGenerator(
                                        client,
                                        model=config.model,
                                        reasoning_effort=config.reasoning_effort,
                                        max_output_tokens=config.max_output_tokens,
                                        request_timeout_seconds=config.request_timeout_seconds,
                                    )
                                    result = run_single_shot_baseline(
                                        task_manifest,
                                        workspace,
                                        generator=generator,
                                        config=config,
                                    )
                                    telemetry = telemetry_from_single_shot(result)
                                    record = baseline_record(
                                        result,
                                        provenance=provenance,
                                        config=config,
                                        limits=AGENT_LIMITS,
                                        task_id=task_id,
                                        repetition=repetition,
                                        position=position,
                                        started_utc=started_utc,
                                        finished_utc=_utc_now(),
                                        lint_configured=workspace.task.lint is not None,
                                    )
                                else:
                                    generator = OpenRouterAgentStepGenerator(
                                        client,
                                        model=config.model,
                                        reasoning_effort=config.reasoning_effort,
                                        max_output_tokens=config.max_output_tokens,
                                        request_timeout_seconds=config.request_timeout_seconds,
                                    )
                                    result = run_agentic_repair(
                                        task_manifest,
                                        workspace,
                                        generator=generator,
                                        config=config,
                                        limits=AGENT_LIMITS,
                                    )
                                    telemetry = telemetry_from_agent_run(result)
                                    record = agent_record(
                                        result,
                                        provenance=provenance,
                                        config=config,
                                        limits=AGENT_LIMITS,
                                        task_id=task_id,
                                        repetition=repetition,
                                        position=position,
                                        started_utc=started_utc,
                                        finished_utc=_utc_now(),
                                        lint_configured=workspace.task.lint is not None,
                                    )
                                output.write(
                                    json.dumps(
                                        record,
                                        sort_keys=True,
                                        ensure_ascii=False,
                                        allow_nan=False,
                                    )
                                    + "\n"
                                )
                                output.flush()
                                completed += 1
                                print(
                                    f"[{task_id} rep={repetition} {strategy}] "
                                    f"success={telemetry.success} "
                                    f"calls={telemetry.model_calls} "
                                    f"tools={telemetry.tool_calls} "
                                    f"cost={telemetry.reported_cost_usd}"
                                )
                            finally:
                                destroy_workspace(workspace)
        finally:
            client.close()

    print(f"experiment id: {provenance.experiment_id}")
    print(f"output file: {args.output}")
    print(f"completed attempts: {completed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
