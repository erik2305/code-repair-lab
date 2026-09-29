"""Manual OpenRouter iterative-agent smoke for dev-001; never run by pytest."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from openai import OpenAI

from coderepair.agent_loop import AgentRunResult, run_agentic_repair
from coderepair.agent_protocol import (
    AgentAction,
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    tool_name_for_action,
)
from coderepair.docker_runner import CommandResult
from coderepair.openrouter_agent_generator import OpenRouterAgentStepGenerator
from coderepair.path_policy import validate_workspace_path
from coderepair.run_config import AgentLimits, RunConfig
from coderepair.run_telemetry import telemetry_from_agent_run
from coderepair.workspace import create_workspace, destroy_workspace

TASK_MANIFEST = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "dev" / "dev-001" / "task.yaml"
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _safe_relative_path(path: str) -> str:
    try:
        return validate_workspace_path(path)
    except ValueError:
        return "<invalid path>"


def _action_summary(action: AgentAction) -> str:
    if isinstance(action, FinishAction):
        return "finish"
    if isinstance(action, ReadFileAction):
        return f"read_file: {_safe_relative_path(action.path)}"
    if isinstance(action, ApplyFileChangesAction):
        paths = ", ".join(_safe_relative_path(change.path) for change in action.changes)
        return f"apply_file_changes: {paths or '(no paths)'}"
    return tool_name_for_action(action)


def _exit_code(check: CommandResult | None) -> int | str:
    return "not run" if check is None else check.exit_code


def _print_report(result: AgentRunResult, config: RunConfig) -> None:
    telemetry = telemetry_from_agent_run(result)
    evaluation = result.evaluation
    print("task: dev-001")
    print("gateway: openrouter")
    print(f"requested model: {config.model}")
    print(f"reasoning effort: {config.reasoning_effort}")
    print("cross-model fallback: disabled")
    print("same-model provider fallback: enabled")
    print("require parameters: enabled")
    print(f"termination reason: {result.termination_reason}")
    print(f"overall success: {evaluation.success}")
    print(f"model calls: {telemetry.model_calls}")
    print(f"tool calls: {telemetry.tool_calls}")
    print(f"aggregate input tokens: {telemetry.input_tokens}")
    print(f"aggregate output tokens: {telemetry.output_tokens}")
    print(f"aggregate total tokens: {telemetry.total_tokens}")
    print(
        f"aggregate model-request latency (seconds): {telemetry.model_latency_seconds}"
    )
    print(f"end-to-end strategy duration (seconds): {telemetry.duration_seconds}")
    print(f"aggregate reported cost USD: {telemetry.reported_cost_usd}")

    print("generations:")
    for step, generation in enumerate(result.generations, start=1):
        usage = generation.usage
        print(f"  {step}. {_action_summary(generation.action)}")
        print(
            f"     returned model: {generation.model}; "
            f"routed provider: {generation.routed_provider}; "
            f"tokens in/out/total: "
            f"{usage.input_tokens}/{usage.output_tokens}/{usage.total_tokens}; "
            f"reported cost USD: {generation.reported_cost_usd}; "
            f"request latency (seconds): {generation.latency_seconds}"
        )

    print("MCP transcript:")
    for step, entry in enumerate(result.transcript, start=1):
        status = "error" if entry.observation.is_error else "ok"
        print(f"  {step}. {entry.observation.tool}: {status}")

    print(f"writable paths respected: {evaluation.writable_paths_respected}")
    print(
        f"unauthorized changes: {', '.join(evaluation.unauthorized_changes) or 'none'}"
    )
    print(f"protected files unchanged: {evaluation.protected_paths_unchanged}")
    print(f"protected changes: {', '.join(evaluation.protected_changes) or 'none'}")
    print(f"reproduction exit code: {_exit_code(evaluation.reproduction)}")
    print(f"full-test exit code: {_exit_code(evaluation.full_test)}")
    print(f"lint exit code: {_exit_code(evaluation.lint)}")
    print(f"overall final success: {evaluation.success}")


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
    limits = AgentLimits(
        max_model_calls=6,
        max_tool_calls=5,
        max_transcript_bytes=100_000,
    )
    with TemporaryDirectory(prefix="coderepair-openrouter-agent-dev001-") as temporary:
        workspace = create_workspace(TASK_MANIFEST, Path(temporary) / "workspace")
        try:
            client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
            try:
                generator = OpenRouterAgentStepGenerator(
                    client,
                    model=config.model,
                    reasoning_effort=config.reasoning_effort,
                    max_output_tokens=config.max_output_tokens,
                    request_timeout_seconds=config.request_timeout_seconds,
                )
                result = run_agentic_repair(
                    TASK_MANIFEST,
                    workspace,
                    generator=generator,
                    config=config,
                    limits=limits,
                )
            finally:
                client.close()
        finally:
            destroy_workspace(workspace)
    _print_report(result, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
