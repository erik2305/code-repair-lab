"""Offline frozen arm semantics, real MCP evidence boundary, and raw records."""

import json
import shutil
import subprocess
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

import coderepair.agent_evidence as shadow_module
import coderepair.baseline as baseline_module
import coderepair.dev_v3_experiment as protocol
import coderepair.mcp_server as mcp_module
from coderepair.agent_generation import AgentStepResult
from coderepair.agent_loop import AgentRunResult
from coderepair.agent_protocol import FinishAction
from coderepair.baseline import render_single_shot_prompt, run_single_shot_baseline
from coderepair.dev_v3_experiment import (
    AGENT_LIMITS,
    ARMS,
    TASK_PROTOCOLS,
    arm_order,
    dev_v3_record,
    run_scripted_repair,
    scripted_shadow_batches,
    validate_selection,
    workspace_context,
)
from coderepair.docker_runner import CommandResult
from coderepair.evaluator import EvaluationResult
from coderepair.experiment import ExperimentProvenance
from coderepair.file_changes import FileChange
from coderepair.generation import GenerationResult, GenerationUsage
from coderepair.repair_context import initial_context_sha256, render_initial_context
from coderepair.run_config import RunConfig
from coderepair.tasks import load_task
from coderepair.workspace import create_workspace

ROOT = Path(__file__).resolve().parents[1]
CONFIG = RunConfig("fake-model", "medium", 4096, 60, 30, 100_000, 200_000, "sha256:ID")
PROVENANCE = ExperimentProvenance(
    "experiment",
    "COMMIT",
    "sha256:ID",
    ("repo@sha256:digest",),
    "3.13",
    "test",
    (("openai", "3.18"), ("mcp", "2"), ("pydantic", "2")),
    "sandbox:dev",
)


def manifest(task="dev-011"):
    return ROOT / "benchmarks/dev" / task / "task.yaml"


def generation(*changes):
    return GenerationResult(
        tuple(changes),
        GenerationUsage(100, 20, 120, 10, 5),
        0.5,
        "fake",
        "returned-model",
        0.01,
        "routed-provider",
    )


def evaluation(success=False):
    command = CommandResult(
        ("python",), 0 if success else 1, "EVALUATOR_SECRET", "", False, 0.2
    )
    return EvaluationResult(success, True, (), command, command, command)


def record(result, arm, *, shadows=()):
    return dev_v3_record(
        result,
        provenance=PROVENANCE,
        config=CONFIG,
        task_id="dev-011",
        arm=arm,
        purpose="smoke",
        repetition=1,
        position=2,
        started_utc="start",
        finished_utc="end",
        lint_configured=True,
        shadow_prefixes=shadows,
    )


@pytest.fixture
def workspace(tmp_path):
    return create_workspace(manifest(), tmp_path / "workspace")


@pytest.fixture
def evaluations(monkeypatch):
    calls = []

    def run(task_manifest, workspace, **options):
        calls.append(
            (
                task_manifest,
                (workspace.root / "scheduler.py").read_text(),
                options,
            )
        )
        return evaluation()

    monkeypatch.setattr(protocol, "evaluate_workspace", run)
    monkeypatch.setattr(baseline_module, "evaluate_workspace", run)
    return calls


def test_frozen_mapping_matches_document_and_actual_withheld_paths():
    expected = (
        ("context-acquisition", "positive", "read_file", "poll_hint.py", True),
        ("context-acquisition", "negative", "read_file", "cursor_codec.py", True),
        ("runtime-diagnostic", "positive", "run_reproduction", None, True),
        ("runtime-diagnostic", "negative", "run_reproduction", None, True),
        ("progressive", "F1→F2", "run_full_tests", None, False),
        ("progressive", "F1→F2", "run_full_tests", None, False),
    )
    document = (ROOT / "benchmarks/dev/DEV_V3_EXECUTION.md").read_text("utf-8")
    rows = {
        line.split("|")[1].strip(" `"): line
        for line in document.splitlines()
        if line.startswith("| `dev-")
    }
    for (task, mapping), (task_class, role, tool, path, s1) in zip(
        TASK_PROTOCOLS.items(),
        expected,
        strict=True,
    ):
        assert (mapping.task_class, mapping.task_role) == (task_class, role)
        assert mapping.s2 == protocol.FixedProbe(tool, path)
        assert mapping.s1 == (mapping.s2 if s1 else None)
        assert mapping.applicable_arms == (ARMS if s1 else (ARMS[0], ARMS[2], ARMS[3]))
        row = rows[task]
        assert f"{task_class} {role}" in row
        assert ("S0, S1, S2, A" if s1 else "S0, S2, A") in row
        probe = f'{tool}("{path}")' if path else tool
        assert row.count(f"`{probe}`") == (2 if s1 else 1)
        if path:
            assert path in load_task(manifest(task)).context_withheld_paths
    assert (
        AGENT_LIMITS.max_model_calls,
        AGENT_LIMITS.max_tool_calls,
        AGENT_LIMITS.max_transcript_bytes,
    ) == (8, 7, 200_000)


def test_s0_and_s1_each_generate_once_same_underlying_context(
    workspace,
    tmp_path,
    evaluations,
):
    context = workspace_context(workspace, CONFIG)
    shared = render_initial_context(context)
    source = (workspace.root / "poll_hint.py").read_text("utf-8")
    original = (workspace.root / "scheduler.py").read_bytes()
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        assert (workspace.root / "scheduler.py").read_bytes() == original
        return generation()

    s1 = run_scripted_repair(
        manifest(),
        workspace,
        generator=generate,
        config=CONFIG,
        arm=ARMS[1],
    )
    assert len(prompts) == 1
    assert prompts[0].count(shared) == 1
    assert json.loads(s1.evidence.model_visible_observation)["result"] == source
    assert s1.evidence.model_visible_observation in prompts[0]
    assert s1.evidence.kind == "pristine"
    assert s1.evidence.tool == "read_file"
    assert len(evaluations) == 1
    pristine = create_workspace(manifest(), tmp_path / "s0")
    s0 = run_single_shot_baseline(
        manifest(),
        pristine,
        generator=generate,
        config=CONFIG,
    )
    assert len(prompts) == 2
    assert prompts[1] == render_single_shot_prompt(context)
    assert s0.initial_context_sha256 == s1.initial_context_sha256
    assert s1.initial_context_sha256 == initial_context_sha256(context)
    assert len(evaluations) == 2  # Failed evaluations never trigger another call.


@pytest.mark.parametrize("empty_second", [False, True])
def test_s2_exact_first_prompt_one_real_probe_cumulative_second(
    workspace,
    monkeypatch,
    evaluations,
    empty_second,
):
    original = workspace_context(workspace, CONFIG)
    shared = render_initial_context(original)
    first_source = "FIRST_GENERATED_SOURCE_SECRET\n"
    second_source = "SECOND_GENERATED_SOURCE_SECRET\n"
    prompts = []
    actual_acquire = protocol.acquire_fixed_evidence
    probe_calls = []

    def acquire(candidate, probe, **kwargs):
        assert (candidate.root / "scheduler.py").read_text() == first_source
        probe_calls.append((probe, kwargs))
        return actual_acquire(candidate, probe, **kwargs)

    monkeypatch.setattr(protocol, "acquire_fixed_evidence", acquire)

    def generate(prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            assert prompt == render_single_shot_prompt(original)
            return generation(FileChange("scheduler.py", first_source))
        assert len(probe_calls) == 1
        assert prompt.count(shared) == 1
        assert first_source.rstrip() in prompt
        assert "ALREADY APPLIED" in prompt
        assert "EVALUATOR_SECRET" not in prompt
        return (
            generation()
            if empty_second
            else generation(
                FileChange("scheduler.py", second_source),
            )
        )

    result = run_scripted_repair(
        manifest(),
        workspace,
        generator=generate,
        config=CONFIG,
        arm=ARMS[2],
    )
    assert len(prompts) == 2
    assert len(probe_calls) == 1
    assert result.evidence.model_visible_observation in prompts[1]
    assert (
        result.generations[0].prompt_sha256
        == sha256(
            render_single_shot_prompt(original).encode(),
        ).hexdigest()
    )
    assert result.initial_context_sha256 == initial_context_sha256(original)
    assert (workspace.root / "scheduler.py").read_text() == (
        first_source if empty_second else second_source
    )
    assert len(evaluations) == 1
    assert evaluations[0][2] == {"image": CONFIG.docker_image, "timeout_seconds": 30}
    raw = record(result, ARMS[2])
    serialized = json.dumps(raw)
    for secret in (first_source.strip(), second_source.strip(), "EVALUATOR_SECRET"):
        assert secret not in serialized
    assert result.evidence.model_visible_observation not in serialized
    assert (
        raw["fixed_evidence"]["observation_sha256"]
        == result.evidence.observation_sha256
    )
    assert raw["model_calls"] == 2
    assert (
        raw["tool_calls_total"],
        raw["adaptive_tool_calls"],
        raw["fixed_evidence_calls"],
    ) == (1, 0, 1)
    assert raw["input_tokens"] == 200
    assert raw["cached_input_tokens"] == 20
    assert raw["reasoning_output_tokens"] == 10
    assert raw["reported_cost_usd"] == 0.02
    assert raw["model_latency_seconds"] == 1
    assert "iterative_occurrence" not in raw


@pytest.mark.parametrize("rejected_stage", [1, 2])
def test_s2_rejected_mutation_never_retries_or_evaluates(
    workspace,
    monkeypatch,
    evaluations,
    rejected_stage,
):
    protected = workspace.root / "tests/test_scheduler.py"
    before = protected.read_bytes()
    original = (workspace.root / "scheduler.py").read_bytes()
    calls = []

    def generate(prompt):
        calls.append(prompt)
        if len(calls) == rejected_stage:
            return generation(FileChange("../outside.py", "REJECTED_SECRET"))
        return generation(FileChange("scheduler.py", "accepted first patch"))

    result = run_scripted_repair(
        manifest(),
        workspace,
        generator=generate,
        config=CONFIG,
        arm=ARMS[2],
    )
    assert len(calls) == rejected_stage
    assert not result.success
    assert result.evaluation is None
    assert evaluations == []
    assert protected.read_bytes() == before
    assert (
        result.evidence is None if rejected_stage == 1 else result.evidence is not None
    )
    assert not result.stages[-1].mutation_applied
    if rejected_stage == 1:
        assert (workspace.root / "scheduler.py").read_bytes() == original
    raw = record(result, ARMS[2])
    assert raw["generations"][-1]["action_paths"] == ["../outside.py"]
    assert "REJECTED_SECRET" not in json.dumps(raw)
    assert str(workspace.root) not in json.dumps(raw)
    assert raw["fixed_evidence_calls"] == rejected_stage - 1


def test_s1_nonzero_reproduction_is_valid_exact_mcp_evidence(tmp_path, monkeypatch):
    workspace = create_workspace(manifest("dev-013"), tmp_path / "workspace")
    events = []

    def run(candidate, argv, **options):
        events.append("probe")
        assert candidate == workspace
        assert argv == workspace.task.reproduction_test
        assert options == {
            "image": "sha256:ID",
            "timeout_seconds": 30,
            "workspace_read_only": True,
        }
        return CommandResult(tuple(argv), 1, "OBSERVATION_SECRET", "", False, 0.1)

    monkeypatch.setattr(mcp_module, "run_in_docker", run)
    monkeypatch.setattr(protocol, "evaluate_workspace", lambda *a, **kw: evaluation())

    def generate(prompt):
        events.append("generation")
        assert "OBSERVATION_SECRET" in prompt
        return generation()

    result = run_scripted_repair(
        manifest("dev-013"),
        workspace,
        generator=generate,
        config=CONFIG,
        arm=ARMS[1],
    )
    assert events == ["probe", "generation"]
    assert result.evidence.exit_code == 1
    assert result.evidence.timed_out is False
    assert result.evidence.is_error is False
    assert result.fixed_evidence_duration_seconds >= 0


def test_fixed_mcp_infrastructure_failure_aborts_before_generation(
    tmp_path, monkeypatch
):
    workspace = create_workspace(manifest("dev-013"), tmp_path / "workspace")

    def fail(*args, **kwargs):
        raise OSError("infrastructure unavailable")

    monkeypatch.setattr(mcp_module, "run_in_docker", fail)
    with pytest.raises(RuntimeError, match="fixed MCP evidence acquisition failed"):
        run_scripted_repair(
            manifest("dev-013"),
            workspace,
            generator=lambda prompt: pytest.fail("must not infer"),
            config=CONFIG,
            arm=ARMS[1],
        )


def test_scripted_invalid_generator_result_is_not_coerced(workspace, evaluations):
    with pytest.raises(ValueError, match="GenerationResult"):
        run_scripted_repair(
            manifest(),
            workspace,
            generator=lambda prompt: [],
            config=CONFIG,
            arm=ARMS[2],
        )
    assert not evaluations


def test_schema_v3_metadata_and_complete_data_aggregation(workspace, evaluations):
    outputs = iter(
        (generation(), replace(generation(), usage=GenerationUsage(None, 20, None)))
    )
    result = run_scripted_repair(
        manifest(),
        workspace,
        generator=lambda prompt: next(outputs),
        config=CONFIG,
        arm=ARMS[2],
    )
    raw = record(result, ARMS[2])
    assert raw["schema_version"] == 3
    assert raw["experiment_protocol"] == "dev-v3"
    assert raw["run_purpose"] == "smoke"
    assert raw["task_class"] == "context-acquisition"
    assert raw["task_role"] == "positive"
    assert raw["applicable_arms"] == list(ARMS)
    assert raw["execution_position_within_task_repetition"] == 2
    assert raw["timestamp_started_utc"] == "start"
    assert raw["timestamp_finished_utc"] == "end"
    assert raw["docker_image_id"] == "sha256:ID"
    assert raw["configured_docker_image"] == "sandbox:dev"
    assert raw["dependency_versions"] == dict(PROVENANCE.dependency_versions)
    assert raw["routing_policy"]["cross_model_fallback"] is False
    assert raw["initial_context_sha256"] == result.initial_context_sha256
    assert raw["strategy_duration_seconds"] == result.duration_seconds
    assert raw["input_tokens"] is None
    assert raw["output_tokens"] == 40
    assert raw["cached_input_tokens"] is None
    assert raw["protected_paths_unchanged"] is True
    assert raw["writable_paths_respected"] is True
    assert raw["unauthorized_changes"] == []
    assert raw["reproduction"]["exit_code"] == 1
    assert raw["full_test"]["exit_code"] == 1
    assert raw["lint"]["exit_code"] == 1
    assert raw["first_patch_applied"] and raw["second_patch_applied"]
    for entry in raw["generations"]:
        assert entry["prompt_sha256"]
        assert entry["patch_sha256"]
        assert entry["returned_model"] == "returned-model"
        assert entry["routed_provider"] == "routed-provider"
    json.dumps(raw, allow_nan=False)


def test_s2_shadow_replays_cumulative_batches_off_live_duration(
    workspace,
    monkeypatch,
    evaluations,
):
    snapshot = manifest().parent / "repo/scheduler.py"
    snapshot_before = snapshot.read_bytes()
    outputs = iter((generation(FileChange("scheduler.py", "prefix one")), generation()))
    result = run_scripted_repair(
        manifest(),
        workspace,
        generator=lambda prompt: next(outputs),
        config=CONFIG,
        arm=ARMS[2],
    )
    duration = result.duration_seconds
    shadow_states = []

    def evaluate(task_manifest, candidate, **options):
        assert candidate.root != workspace.root
        assert options == {"image": "sha256:ID", "timeout_seconds": 30}
        shadow_states.append((candidate.root / "scheduler.py").read_text())
        return evaluation(True)

    monkeypatch.setattr(shadow_module, "evaluate_workspace", evaluate)
    shadows = shadow_module.shadow_evaluate_batches(
        manifest(),
        scripted_shadow_batches(result),
        image=CONFIG.docker_image,
        timeout_seconds=CONFIG.evaluator_timeout_seconds,
    )
    assert shadow_states == ["prefix one", "prefix one"]
    assert len(shadows) == 2
    assert shadows[0].workspace_state_sha256 == shadows[1].workspace_state_sha256
    assert snapshot.read_bytes() == snapshot_before
    assert result.duration_seconds == duration
    assert "EVALUATOR_SECRET" not in result.evidence.model_visible_observation
    raw = record(result, ARMS[2], shadows=shadows)
    assert raw["first_patch_shadow_success"] is True
    assert len(raw["shadow_prefixes"]) == 2


def test_agent_record_keeps_classifier_and_context_identity(workspace):
    context_hash = initial_context_sha256(workspace_context(workspace, CONFIG))
    step = AgentStepResult(
        FinishAction(),
        GenerationUsage(1, 1, 2),
        0.1,
        "fake",
        "fake",
        prompt_sha256="a" * 64,
    )
    result = AgentRunResult((step,), (), "finish", evaluation(), 1.0, context_hash)
    raw = record(result, ARMS[3])
    assert raw["initial_context_sha256"] == context_hash
    assert raw["agent_limits"] == {
        "max_model_calls": 8,
        "max_tool_calls": 7,
        "max_transcript_bytes": 200_000,
    }
    assert raw["iterative_occurrence"] == "none"
    assert raw["adaptive_tool_calls"] == result.tool_calls


@pytest.mark.parametrize("task", tuple(TASK_PROTOCOLS))
def test_counterbalancing_deterministic_complete_balanced(task):
    applicable = TASK_PROTOCOLS[task].applicable_arms
    orders = [
        arm_order(task, repetition) for repetition in range(1, len(applicable) + 1)
    ]
    assert orders == [
        arm_order(task, repetition) for repetition in range(1, len(applicable) + 1)
    ]
    for order in orders:
        assert len(order) == len(set(order)) == len(applicable)
        assert set(order) == set(applicable)
    for position in range(len(applicable)):
        assert {order[position] for order in orders} == set(applicable)


@pytest.mark.parametrize(
    "purpose,tasks,arms,repetitions",
    [
        ("comparison", tuple(TASK_PROTOCOLS), (), 4),
        ("comparison", tuple(TASK_PROTOCOLS)[:-1], (), 5),
        ("comparison", tuple(TASK_PROTOCOLS), (ARMS[0],), 5),
        ("comparison", tuple(TASK_PROTOCOLS), ("unknown",), 5),
        ("smoke", ("dev-015",), (ARMS[1],), 1),
        ("smoke", ("dev-011",), (), 0),
        ("smoke", (), (), 1),
    ],
)
def test_selection_guards(purpose, tasks, arms, repetitions):
    with pytest.raises(ValueError):
        validate_selection(purpose, tasks, arms, repetitions)


def test_complete_comparison_and_smoke_subset_are_accepted():
    validate_selection("comparison", tuple(TASK_PROTOCOLS), ARMS, 5)
    validate_selection("comparison", tuple(TASK_PROTOCOLS), (), 5)
    validate_selection("smoke", ("dev-011",), ARMS, 1)
    validate_selection("smoke", ("dev-015",), (ARMS[0], ARMS[2]), 1)


def test_s1_source_and_exact_observation_only_in_prompt_not_record(
    workspace, evaluations
):
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        return generation(FileChange("scheduler.py", "GENERATED_SOURCE_SENTINEL"))

    result = run_scripted_repair(
        manifest(),
        workspace,
        generator=generate,
        config=CONFIG,
        arm=ARMS[1],
    )
    raw = record(result, ARMS[1])
    payload = json.dumps(raw)
    assert "GENERATED_SOURCE_SENTINEL" not in payload
    assert result.evidence.model_visible_observation not in payload
    assert (workspace.root / "poll_hint.py").read_text() not in payload
    assert (
        raw["generations"][0]["prompt_sha256"]
        == sha256(prompts[0].encode()).hexdigest()
    )
    assert raw["fixed_evidence"]["kind"] == "pristine"
    assert (
        raw["tool_calls_total"],
        raw["adaptive_tool_calls"],
        raw["fixed_evidence_calls"],
    ) == (1, 0, 1)


def test_live_duration_includes_fixed_acquisition_not_shadow(
    workspace,
    monkeypatch,
    evaluations,
):
    clock = iter((0.0, 2.0, 5.0, 9.0))
    monkeypatch.setattr(protocol, "perf_counter", lambda: next(clock))
    result = run_scripted_repair(
        manifest(),
        workspace,
        generator=lambda prompt: generation(),
        config=CONFIG,
        arm=ARMS[2],
    )
    assert result.duration_seconds == 9
    assert result.fixed_evidence_duration_seconds == 3
    monkeypatch.setattr(
        shadow_module, "evaluate_workspace", lambda *a, **kw: evaluation()
    )
    shadow_module.shadow_evaluate_batches(
        manifest(),
        scripted_shadow_batches(result),
        image=CONFIG.docker_image,
        timeout_seconds=30,
    )
    assert result.duration_seconds == 9


@pytest.mark.parametrize("task", ["dev-015", "dev-016"])
def test_progressive_probe_exactly_full_suite_after_first_patch(
    tmp_path, monkeypatch, task
):
    candidate = create_workspace(manifest(task), tmp_path / "workspace")
    writable = candidate.task.writable_paths[0]
    calls = []

    def run(workspace, argv, **options):
        assert (workspace.root / writable).read_text() == "FIRST_PATCH"
        assert argv == workspace.task.full_test
        calls.append(argv)
        return CommandResult(tuple(argv), 1, "F2_OBSERVATION", "", False, 0.1)

    monkeypatch.setattr(mcp_module, "run_in_docker", run)
    monkeypatch.setattr(protocol, "evaluate_workspace", lambda *a, **kw: evaluation())
    outputs = iter((generation(FileChange(writable, "FIRST_PATCH")), generation()))
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        return next(outputs)

    result = run_scripted_repair(
        manifest(task),
        candidate,
        generator=generate,
        config=CONFIG,
        arm=ARMS[2],
    )
    assert len(calls) == 1
    assert len(prompts) == 2
    assert "F2_OBSERVATION" not in prompts[0]
    assert "F2_OBSERVATION" in prompts[1]
    assert result.evidence.tool == "run_full_tests"
    raw = dev_v3_record(
        result,
        provenance=PROVENANCE,
        config=CONFIG,
        task_id=task,
        arm=ARMS[2],
        purpose="smoke",
        repetition=1,
        position=1,
        started_utc="start",
        finished_utc="end",
        lint_configured=True,
    )
    assert ARMS[1] not in raw["applicable_arms"]


@pytest.fixture(scope="module")
def docker_image():
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI unavailable")
    try:
        daemon = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        if daemon.returncode != 0:
            pytest.skip("Docker daemon unavailable")
        image = subprocess.run(
            ["docker", "image", "inspect", "coderepair-lab-sandbox:dev"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if image.returncode != 0:
            pytest.skip("development sandbox image unavailable")
        return json.loads(image.stdout)[0]["Id"]
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("Docker/image inspection unavailable")


def test_docker_s1_original_diagnostic_then_one_correct_repair(tmp_path, docker_image):
    task = "dev-013"
    candidate = create_workspace(manifest(task), tmp_path / "workspace")
    snapshot = manifest(task).parent / "repo/loader.py"
    before = snapshot.read_bytes()
    source = (
        (candidate.root / "loader.py")
        .read_text()
        .replace(
            "return parse_binary(payload)",
            'return parse_binary(payload.rstrip(b"\\r\\n"))',
        )
    )
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        return generation(FileChange("loader.py", source))

    result = run_scripted_repair(
        manifest(task),
        candidate,
        generator=generate,
        config=replace(CONFIG, docker_image=docker_image),
        arm=ARMS[1],
    )
    assert len(prompts) == 1
    assert result.evidence.exit_code == 1
    assert result.evidence.timed_out is False
    assert result.success
    assert all(
        command.exit_code == 0
        for command in (
            result.evaluation.reproduction,
            result.evaluation.full_test,
            result.evaluation.lint,
        )
    )
    assert snapshot.read_bytes() == before


def test_docker_s2_progressive_probe_and_shadow_measurements(tmp_path, docker_image):
    task = "dev-015"
    candidate = create_workspace(manifest(task), tmp_path / "workspace")
    first = (
        (candidate.root / "authorizer.py")
        .read_text()
        .replace(
            "checked_group = require_group(group)\n"
            "    canonical_group = expand_alias(checked_group)",
            "canonical_group = require_group(expand_alias(group))",
        )
    )
    second = (
        (candidate.root / "policy.py")
        .read_text()
        .replace(
            "    for rule in rules:\n"
            '        if rule.group == group and rule.resource in (resource, "*"):\n'
            '            return rule.effect == "allow"\n    return False',
            "    matching = [\n        rule for rule in rules\n"
            '        if rule.group == group and rule.resource in (resource, "*")\n'
            "    ]\n"
            '    if any(rule.effect == "deny" for rule in matching):\n'
            "        return False\n"
            '    return any(rule.effect == "allow" for rule in matching)',
        )
    )
    outputs = iter(
        (
            generation(FileChange("authorizer.py", first)),
            generation(FileChange("policy.py", second)),
        )
    )
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        return next(outputs)

    result = run_scripted_repair(
        manifest(task),
        candidate,
        generator=generate,
        config=replace(CONFIG, docker_image=docker_image),
        arm=ARMS[2],
    )
    assert len(prompts) == 2
    assert result.evidence.exit_code == 1
    assert (
        "explicit deny must override allow" in result.evidence.model_visible_observation
    )
    assert result.success
    duration = result.duration_seconds
    shadows = shadow_module.shadow_evaluate_batches(
        manifest(task),
        scripted_shadow_batches(result),
        image=docker_image,
        timeout_seconds=30,
    )
    assert [prefix.evaluation_success for prefix in shadows] == [False, True]
    assert result.duration_seconds == duration
