"""Manual frozen DEV-v3 orchestration. No provider work at import time."""

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

from coderepair.agent_evidence import shadow_evaluate_batches, shadow_evaluate_prefixes
from coderepair.agent_loop import run_agentic_repair
from coderepair.baseline import run_single_shot_baseline
from coderepair.dev_v3_experiment import (
    AGENT_LIMITS,
    ARMS,
    TASK_PROTOCOLS,
    _generate,
    arm_order,
    dev_v3_record,
    run_scripted_repair,
    scripted_shadow_batches,
    validate_mapping,
    validate_selection,
    workspace_context,
)
from coderepair.experiment import (
    ExperimentProvenance,
    open_new_output,
    pin_docker_image,
    require_clean_git,
)
from coderepair.openrouter_agent_generator import OpenRouterAgentStepGenerator
from coderepair.openrouter_generator import OpenRouterRepairGenerator
from coderepair.repair_context import initial_context_sha256
from coderepair.run_config import RunConfig
from coderepair.tasks import load_task
from coderepair.workspace import create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _selectors(value: str | None, defaults: tuple[str, ...]) -> tuple[str, ...]:
    return defaults if value is None else tuple(value.split(","))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen DEV-v3 protocol")
    parser.add_argument("--purpose", choices=("smoke", "comparison"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort", required=True)
    parser.add_argument("--repetitions", type=int, required=True)
    parser.add_argument("--tasks", help="comma-separated task IDs (default: all six)")
    parser.add_argument("--arms", help="comma-separated arms (default: all applicable)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    tasks = _selectors(args.tasks, tuple(TASK_PROTOCOLS))
    arms = _selectors(args.arms, ())
    validate_selection(args.purpose, tasks, arms, args.repetitions)
    # Preserve canonical task order even when the selector is supplied reordered.
    tasks = tuple(task for task in TASK_PROTOCOLS if task in tasks)
    config = RunConfig(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        max_output_tokens=4096,
        request_timeout_seconds=60,
        evaluator_timeout_seconds=30,
        max_file_bytes=100_000,
        max_total_bytes=200_000,
        docker_image="coderepair-lab-sandbox:dev",
    )
    commit = require_clean_git(PROJECT_ROOT)
    manifests = {
        task: PROJECT_ROOT / "benchmarks" / "dev" / task / "task.yaml" for task in tasks
    }
    # Validate every manifest before materializing any selected context.
    for task, manifest in manifests.items():
        if load_task(manifest).id != task:
            raise ValueError("manifest ID does not match frozen task mapping")
    context_digests: dict[str, str] = {}
    for task, manifest in manifests.items():
        with TemporaryDirectory(prefix="coderepair-v3-preflight-") as temporary:
            workspace = create_workspace(manifest, Path(temporary) / "workspace")
            try:
                context = workspace_context(workspace, config)
                validate_mapping(workspace)
                context_digests[task] = initial_context_sha256(context)
            finally:
                destroy_workspace(workspace)
    pinned, image_id, digests = pin_docker_image(config)
    provenance = ExperimentProvenance(
        experiment_id=datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"),
        git_commit=commit,
        docker_image_id=image_id,
        docker_repo_digests=digests,
        python_version=platform.python_version(),
        platform=platform.platform(),
        configured_docker_image=config.docker_image,
    )
    # Exclusive output creation is part of preflight, before constructing a client.
    with open_new_output(args.output) as output:
        load_dotenv()
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required")
        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
        try:
            generator_options = dict(
                model=pinned.model,
                reasoning_effort=pinned.reasoning_effort,
                max_output_tokens=pinned.max_output_tokens,
                request_timeout_seconds=pinned.request_timeout_seconds,
            )
            for task in tasks:
                manifest = manifests[task]
                for repetition in range(1, args.repetitions + 1):
                    for position, arm in enumerate(
                        arm_order(task, repetition, arms), 1
                    ):
                        with TemporaryDirectory(prefix="coderepair-v3-") as temporary:
                            workspace = create_workspace(
                                manifest,
                                Path(temporary) / "workspace",
                            )
                            try:
                                observed = initial_context_sha256(
                                    workspace_context(workspace, pinned),
                                )
                                if observed != context_digests[task]:
                                    raise RuntimeError(
                                        "underlying initial context drift"
                                    )
                                started = _utc_now()
                                if arm == ARMS[3]:
                                    generator = OpenRouterAgentStepGenerator(
                                        client,
                                        **generator_options,
                                    )
                                    result = run_agentic_repair(
                                        manifest,
                                        workspace,
                                        generator=generator,
                                        config=pinned,
                                        limits=AGENT_LIMITS,
                                    )
                                else:
                                    repair_generator = OpenRouterRepairGenerator(
                                        client,
                                        **generator_options,
                                    )
                                    if arm == ARMS[0]:
                                        # Capture exact prompt identity even for a
                                        # generator which omits its optional digest.
                                        result = run_single_shot_baseline(
                                            manifest,
                                            workspace,
                                            generator=lambda prompt: _generate(
                                                repair_generator,
                                                prompt,
                                            ),
                                            config=pinned,
                                        )
                                    else:
                                        result = run_scripted_repair(
                                            manifest,
                                            workspace,
                                            generator=repair_generator,
                                            config=pinned,
                                            arm=arm,
                                        )
                                finished = _utc_now()
                                if (
                                    result.initial_context_sha256
                                    != context_digests[task]
                                ):
                                    raise RuntimeError("strategy initial context drift")
                                # Measurement-only replay, after live duration ends.
                                shadows = ()
                                if arm == ARMS[3]:
                                    shadows = shadow_evaluate_prefixes(
                                        manifest,
                                        result,
                                        image=pinned.docker_image,
                                        timeout_seconds=pinned.evaluator_timeout_seconds,
                                    )
                                elif arm == ARMS[2]:
                                    shadows = shadow_evaluate_batches(
                                        manifest,
                                        scripted_shadow_batches(result),
                                        image=pinned.docker_image,
                                        timeout_seconds=pinned.evaluator_timeout_seconds,
                                    )
                                record = dev_v3_record(
                                    result,
                                    provenance=provenance,
                                    config=pinned,
                                    task_id=task,
                                    arm=arm,
                                    purpose=args.purpose,
                                    repetition=repetition,
                                    position=position,
                                    started_utc=started,
                                    finished_utc=finished,
                                    lint_configured=workspace.task.lint is not None,
                                    shadow_prefixes=shadows,
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
                                print(
                                    f"[{task} rep={repetition} {arm}] "
                                    f"success={result.success}"
                                )
                            finally:
                                destroy_workspace(workspace)
        finally:
            client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
