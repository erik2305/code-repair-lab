"""Frozen DEV-v3 arms, fixed MCP evidence, and source-free prospective records."""

import asyncio
import json
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from types import MappingProxyType
from typing import Literal

from mcp import Client

from coderepair.agent_evidence import ShadowPrefixResult, patch_metadata
from coderepair.agent_loop import AgentRunResult
from coderepair.agent_protocol import ApplyFileChangesAction
from coderepair.baseline import (
    RepairGenerator,
    SingleShotResult,
    _safe_mutation_error,
    render_single_shot_prompt,
)
from coderepair.evaluator import EvaluationResult, evaluate_workspace
from coderepair.experiment import (
    ExperimentProvenance,
    _evaluation_fields,
    agent_record,
    baseline_record,
)
from coderepair.file_changes import FileChange, apply_file_changes
from coderepair.generation import GenerationResult
from coderepair.mcp_server import build_mcp_server, raise_docker_tool_failure
from coderepair.openrouter_response import openrouter_routing_policy
from coderepair.repair_context import (
    InitialRepairContext,
    build_initial_context,
    initial_context_sha256,
    render_initial_context,
)
from coderepair.run_config import AgentLimits, RunConfig
from coderepair.run_telemetry import _sum_complete
from coderepair.tasks import load_task
from coderepair.workspace import Workspace

Arm = Literal[
    "initial_single_shot",
    "evidence_enriched_single_shot",
    "scripted_feedback_two_shot",
    "agentic",
]
ARMS: tuple[Arm, ...] = (
    "initial_single_shot",
    "evidence_enriched_single_shot",
    "scripted_feedback_two_shot",
    "agentic",
)
AGENT_LIMITS = AgentLimits(8, 7, 200_000)


@dataclass(frozen=True, slots=True)
class FixedProbe:
    tool: Literal["read_file", "run_reproduction", "run_full_tests"]
    path: str | None = None


@dataclass(frozen=True, slots=True)
class TaskProtocol:
    task_class: str
    task_role: str
    applicable_arms: tuple[Arm, ...]
    s1: FixedProbe | None
    s2: FixedProbe


TASK_PROTOCOLS = MappingProxyType(
    {
        "dev-011": TaskProtocol(
            "context-acquisition",
            "positive",
            ARMS,
            FixedProbe("read_file", "poll_hint.py"),
            FixedProbe("read_file", "poll_hint.py"),
        ),
        "dev-012": TaskProtocol(
            "context-acquisition",
            "negative",
            ARMS,
            FixedProbe("read_file", "cursor_codec.py"),
            FixedProbe("read_file", "cursor_codec.py"),
        ),
        "dev-013": TaskProtocol(
            "runtime-diagnostic",
            "positive",
            ARMS,
            FixedProbe("run_reproduction"),
            FixedProbe("run_reproduction"),
        ),
        "dev-014": TaskProtocol(
            "runtime-diagnostic",
            "negative",
            ARMS,
            FixedProbe("run_reproduction"),
            FixedProbe("run_reproduction"),
        ),
        "dev-015": TaskProtocol(
            "progressive",
            "F1→F2",
            (ARMS[0], ARMS[2], ARMS[3]),
            None,
            FixedProbe("run_full_tests"),
        ),
        "dev-016": TaskProtocol(
            "progressive",
            "F1→F2",
            (ARMS[0], ARMS[2], ARMS[3]),
            None,
            FixedProbe("run_full_tests"),
        ),
    }
)


def validate_selection(
    purpose: str,
    tasks: tuple[str, ...],
    arms: tuple[str, ...],
    repetitions: int,
) -> None:
    """An omitted arm selector means all applicable arms, not impossible pairs."""
    if purpose not in ("smoke", "comparison"):
        raise ValueError("purpose must be smoke or comparison")
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    if not tasks or len(set(tasks)) != len(tasks) or set(tasks) - TASK_PROTOCOLS.keys():
        raise ValueError("unknown, duplicate, or empty task selection")
    if len(set(arms)) != len(arms) or set(arms) - set(ARMS):
        raise ValueError("unknown or duplicate arm selection")
    if purpose == "comparison":
        if repetitions < 5 or set(tasks) != set(TASK_PROTOCOLS):
            raise ValueError("comparison requires all six tasks and at least 5 repeats")
        if arms and set(arms) != set(ARMS):
            raise ValueError("comparison requires all applicable arms")
    elif arms:
        for task in tasks:
            if set(arms) - set(TASK_PROTOCOLS[task].applicable_arms):
                raise ValueError(f"requested arm is not applicable to {task}")


def arm_order(
    task_id: str, repetition: int, arms: tuple[str, ...] = ()
) -> tuple[Arm, ...]:
    """Rotate canonical applicable arms by frozen task index + one-based repeat."""
    applicable = tuple(
        arm
        for arm in TASK_PROTOCOLS[task_id].applicable_arms
        if not arms or arm in arms
    )
    offset = (tuple(TASK_PROTOCOLS).index(task_id) + repetition - 1) % len(applicable)
    return applicable[offset:] + applicable[:offset]


def workspace_context(workspace: Workspace, config: RunConfig) -> InitialRepairContext:
    return build_initial_context(
        workspace,
        max_file_bytes=config.max_file_bytes,
        max_total_bytes=config.max_total_bytes,
    )


def validate_mapping(workspace: Workspace) -> None:
    """Read probes must be real explicitly withheld files in the frozen task."""
    protocol = TASK_PROTOCOLS[workspace.task.id]
    for probe in (protocol.s1, protocol.s2):
        if probe is not None and probe.tool == "read_file":
            if probe.path not in workspace.task.context_withheld_paths:
                raise ValueError("fixed read evidence is not a withheld task path")
            target = workspace.root / probe.path
            if target.is_symlink() or target.is_junction() or not target.is_file():
                raise ValueError("fixed read evidence is not an ordinary file")


@dataclass(frozen=True, slots=True)
class FixedEvidence:
    kind: str
    tool: str
    path: str | None
    is_error: bool
    exit_code: int | None
    timed_out: bool | None
    model_visible_observation: str
    observation_sha256: str

    def metadata(self) -> dict[str, object]:
        return {
            key: value
            for key, value in asdict(self).items()
            if key != "model_visible_observation"
        }


def acquire_fixed_evidence(
    workspace: Workspace,
    probe: FixedProbe,
    *,
    config: RunConfig,
    kind: str,
) -> FixedEvidence:
    """One real MCP call with identical bounded/sanitized agent-visible semantics."""
    server = build_mcp_server(
        workspace,
        image=config.docker_image,
        timeout_seconds=config.evaluator_timeout_seconds,
    )

    async def acquire():
        async with Client(server, raise_exceptions=True) as client:
            return await client.call_tool(
                probe.tool,
                {"path": probe.path} if probe.path is not None else {},
            )

    result = asyncio.run(acquire())
    if result.is_error:
        error_text = "\n".join(
            block.text for block in result.content if block.type == "text"
        )
        raise_docker_tool_failure(probe.tool, True, error_text)
        raise RuntimeError("fixed MCP evidence acquisition failed")
    structured = result.structured_content
    content = (
        json.dumps(
            structured, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        if structured is not None
        else "\n".join(block.text for block in result.content if block.type == "text")
    )
    outcome = structured if isinstance(structured, dict) else {}
    return FixedEvidence(
        kind,
        probe.tool,
        probe.path,
        False,
        outcome.get("exit_code"),
        outcome.get("timed_out"),
        content,
        sha256(content.encode("utf-8")).hexdigest(),
    )


def _render_evidence(evidence: FixedEvidence) -> str:
    return (
        "\nMECHANICALLY ACQUIRED INFORMATION\n"
        + json.dumps(evidence.metadata(), sort_keys=True, ensure_ascii=False)
        + "\nEXACT MODEL-VISIBLE OBSERVATION\n"
        + evidence.model_visible_observation
        + "\n"
    )


def render_enriched_prompt(
    context: InitialRepairContext, evidence: FixedEvidence
) -> str:
    return render_single_shot_prompt(context) + _render_evidence(evidence)


def render_second_prompt(
    context: InitialRepairContext,
    first: GenerationResult,
    evidence: FixedEvidence,
) -> str:
    return (
        render_initial_context(context)
        + "\nFIRST PROPOSED REPAIR BATCH — ALREADY APPLIED\n"
        + json.dumps(
            [asdict(change) for change in first.changes],
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
        + _render_evidence(evidence)
        + "\nFINAL CUMULATIVE REPAIR\nPropose additional/final file changes on top "
        "of the current workspace. Only writable files may change; protected files "
        "may be inspected but not changed. An empty batch keeps the first repair "
        "unchanged. No additional inspection or feedback is available.\n"
    )


@dataclass(frozen=True, slots=True)
class MutationStage:
    mutation_applied: bool
    mutation_error: str | None


@dataclass(frozen=True, slots=True)
class ScriptedResult:
    generations: tuple[GenerationResult, ...]
    stages: tuple[MutationStage, ...]
    evidence: FixedEvidence | None
    evaluation: EvaluationResult | None
    duration_seconds: float
    fixed_evidence_duration_seconds: float | None
    initial_context_sha256: str

    @property
    def success(self) -> bool:
        return self.evaluation is not None and self.evaluation.success


def _generate(generator: RepairGenerator, prompt: str) -> GenerationResult:
    generation = generator(prompt)
    if not isinstance(generation, GenerationResult):
        raise ValueError("generator must return a GenerationResult")
    digest = sha256(prompt.encode("utf-8")).hexdigest()
    if generation.prompt_sha256 not in (None, digest):
        raise ValueError("generator reported an inconsistent prompt digest")
    return replace(generation, prompt_sha256=digest)


def _mutate(workspace: Workspace, generation: GenerationResult) -> MutationStage:
    try:
        apply_file_changes(workspace, generation.changes)
    except (ValueError, OSError) as error:
        return MutationStage(False, _safe_mutation_error(error, workspace.root))
    return MutationStage(True, None)


def run_scripted_repair(
    task_manifest: Path,
    workspace: Workspace,
    *,
    generator: RepairGenerator,
    config: RunConfig,
    arm: Literal["evidence_enriched_single_shot", "scripted_feedback_two_shot"],
) -> ScriptedResult:
    """S1: pristine evidence/one call. S2: S0 call/patch/fixed probe/second call."""
    if load_task(task_manifest) != workspace.task:
        raise ValueError("workspace task does not match the supplied task manifest")
    protocol = TASK_PROTOCOLS[workspace.task.id]
    if arm not in (ARMS[1], ARMS[2]) or arm not in protocol.applicable_arms:
        raise ValueError("scripted arm is not applicable to this task")
    validate_mapping(workspace)
    started = perf_counter()
    context = workspace_context(workspace, config)
    digest = initial_context_sha256(context)
    evidence = None
    evidence_duration = None
    generations: list[GenerationResult] = []
    stages: list[MutationStage] = []

    def acquire(probe: FixedProbe, kind: str) -> FixedEvidence:
        nonlocal evidence_duration
        evidence_started = perf_counter()
        packet = acquire_fixed_evidence(workspace, probe, config=config, kind=kind)
        evidence_duration = perf_counter() - evidence_started
        return packet

    if arm == ARMS[1]:
        evidence = acquire(protocol.s1, "pristine")
        prompt = render_enriched_prompt(context, evidence)
    else:
        prompt = render_single_shot_prompt(context)
    generations.append(_generate(generator, prompt))
    stages.append(_mutate(workspace, generations[0]))
    if stages[0].mutation_applied and arm == ARMS[2]:
        evidence = acquire(protocol.s2, "post_patch_1")
        generations.append(
            _generate(
                generator,
                render_second_prompt(context, generations[0], evidence),
            )
        )
        stages.append(_mutate(workspace, generations[1]))
    evaluation = None
    if all(stage.mutation_applied for stage in stages):
        evaluation = evaluate_workspace(
            task_manifest,
            workspace,
            image=config.docker_image,
            timeout_seconds=config.evaluator_timeout_seconds,
        )
    return ScriptedResult(
        tuple(generations),
        tuple(stages),
        evidence,
        evaluation,
        perf_counter() - started,
        evidence_duration,
        digest,
    )


def scripted_shadow_batches(
    result: ScriptedResult,
) -> tuple[tuple[FileChange, ...], ...]:
    return tuple(
        generation.changes
        for generation, stage in zip(result.generations, result.stages, strict=True)
        if stage.mutation_applied
    )


def dev_v3_record(
    result: SingleShotResult | ScriptedResult | AgentRunResult,
    *,
    provenance: ExperimentProvenance,
    config: RunConfig,
    task_id: str,
    arm: Arm,
    purpose: str,
    repetition: int,
    position: int,
    started_utc: str,
    finished_utc: str,
    lint_configured: bool,
    shadow_prefixes: tuple[ShadowPrefixResult, ...] = (),
    inter_attempt_delay_seconds: float = 0,
) -> dict[str, object]:
    """Prospective schema v3; never persist source, prompts, or observation text."""
    protocol = TASK_PROTOCOLS[task_id]
    if arm not in protocol.applicable_arms:
        raise ValueError("record arm is not applicable")
    common = dict(
        provenance=provenance,
        config=config,
        limits=AGENT_LIMITS,
        task_id=task_id,
        repetition=repetition,
        position=position,
        started_utc=started_utc,
        finished_utc=finished_utc,
        lint_configured=lint_configured,
    )
    if isinstance(result, AgentRunResult):
        record = agent_record(result, **common, shadow_prefixes=shadow_prefixes)
        record["mutation_stages"] = [
            {
                "mutation_applied": not entry.observation.is_error,
                "mutation_error": (
                    "MCP mutation rejected" if entry.observation.is_error else None
                ),
            }
            for entry in result.transcript
            if isinstance(entry.action, ApplyFileChangesAction)
        ]
        adaptive = len(result.transcript)
        fixed = 0
    elif isinstance(result, SingleShotResult):
        record = baseline_record(result, **common)
        # Schema 2 stores its one generation flat; schema 3 always uses a sequence.
        record["generations"] = [_generation_record(result.generation, 1)]
        record["mutation_stages"] = [
            asdict(
                MutationStage(
                    result.mutation_applied,
                    result.mutation_error,
                )
            )
        ]
        adaptive = fixed = 0
    else:
        record = {
            **asdict(provenance),
            **asdict(config),
            "dependency_versions": dict(provenance.dependency_versions),
            "requested_model": config.model,
            "routing_policy": openrouter_routing_policy(),
            "timestamp_started_utc": started_utc,
            "timestamp_finished_utc": finished_utc,
            "success": result.success,
            "initial_context_sha256": result.initial_context_sha256,
            "model_calls": len(result.generations),
            "generations": [
                _generation_record(generation, step)
                for step, generation in enumerate(result.generations, 1)
            ],
            "mutation_stages": [asdict(stage) for stage in result.stages],
            "termination_reason": (
                "completed" if result.evaluation is not None else "mutation_rejected"
            ),
            **_evaluation_fields(result.evaluation, lint_configured),
        }
        for field in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "reasoning_output_tokens",
        ):
            record[field] = _sum_complete(
                tuple(
                    getattr(generation.usage, field)
                    for generation in result.generations
                )
            )
        for name, attribute in (
            ("model_latency_seconds", "latency_seconds"),
            ("reported_cost_usd", "reported_cost_usd"),
        ):
            record[name] = _sum_complete(
                tuple(
                    getattr(generation, attribute) for generation in result.generations
                )
            )
        adaptive = 0
        fixed = int(result.evidence is not None)
        record["fixed_evidence"] = (
            result.evidence.metadata() if result.evidence is not None else None
        )
        if arm == ARMS[2]:
            record.update(
                first_patch_applied=result.stages[0].mutation_applied,
                fixed_probe_executed=result.evidence is not None,
                second_patch_applied=(
                    result.stages[1].mutation_applied
                    if len(result.stages) == 2
                    else False
                ),
                first_patch_shadow_success=(
                    shadow_prefixes[0].evaluation_success if shadow_prefixes else None
                ),
            )
    record.pop("execution_position_within_pair", None)
    record.pop("strategy", None)
    record.update(
        schema_version=3,
        experiment_protocol="dev-v3",
        run_purpose=purpose,
        task_id=task_id,
        task_class=protocol.task_class,
        task_role=protocol.task_role,
        applicable_arms=list(protocol.applicable_arms),
        arm=arm,
        repetition=repetition,
        execution_position=position,
        execution_position_within_task_repetition=position,
        tool_calls_total=adaptive + fixed,
        adaptive_tool_calls=adaptive,
        fixed_evidence_calls=fixed,
        strategy_duration_seconds=result.duration_seconds,
        fixed_evidence_duration_seconds=(
            result.fixed_evidence_duration_seconds
            if isinstance(result, ScriptedResult)
            else None
        ),
        agent_limits=asdict(AGENT_LIMITS) if arm == ARMS[3] else None,
        shadow_prefixes=[asdict(prefix) for prefix in shadow_prefixes],
        inter_attempt_delay_seconds=inter_attempt_delay_seconds,
    )
    if "termination_reason" not in record:
        record["termination_reason"] = (
            "completed" if result.evaluation is not None else "mutation_rejected"
        )
    return record


def _generation_record(generation: GenerationResult, step: int) -> dict[str, object]:
    digest, changes = patch_metadata(generation.changes)
    return {
        "step": step,
        "prompt_sha256": generation.prompt_sha256,
        "action_type": "apply_file_changes",
        "action_paths": [change.path for change in generation.changes],
        "patch_sha256": digest,
        "changes": changes,
        **asdict(generation.usage),
        "latency_seconds": generation.latency_seconds,
        "reported_cost_usd": generation.reported_cost_usd,
        "gateway_provider": generation.provider,
        "returned_model": generation.model,
        "routed_provider": generation.routed_provider,
    }
