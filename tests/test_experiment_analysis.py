"""Offline generated evidence: integrity, mechanisms, arithmetic and safe exports."""

import csv
import io
import json
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal

import pytest

from coderepair.dev_v3_experiment import AGENT_LIMITS, ARMS, TASK_PROTOCOLS, arm_order
from coderepair.experiment_analysis import (
    CSV_FIELDS,
    analyze_experiments,
    render_attempts_csv,
    render_report,
    stable_json,
    write_analysis,
)
from coderepair.openrouter_response import openrouter_routing_policy
from scripts.analyze_experiments import main


def command(exit_code=0):
    return {
        "configured": True,
        "present": True,
        "exit_code": exit_code,
        "timed_out": False,
        "duration_seconds": 0.1,
    }


def shadow(success=False):
    return {
        "patch_index": 1,
        "evaluation_success": success,
        "reproduction_exit_code": 0 if success else 1,
        "reproduction_timed_out": False,
        "full_test_exit_code": 0 if success else 1,
        "full_test_timed_out": False,
    }


def generation(action="apply_file_changes", changes=True):
    return {
        "prompt_sha256": "b" * 64,
        "action_type": action,
        "changes": [{"path": "../unsafe.py", "content_sha256": "c" * 64}]
        if changes
        else [],
        "returned_model": "returned-model",
        "routed_provider": "provider",
    }


def records():
    result = []
    for task, protocol in TASK_PROTOCOLS.items():
        for repeat in range(1, 6):
            for arm in protocol.applicable_arms:
                generations = [generation()]
                prefixes = []
                if arm == ARMS[2]:
                    generations.append(generation(changes=False))
                    prefixes = [shadow(False), {**shadow(True), "patch_index": 2}]
                elif arm == ARMS[3]:
                    generations += [
                        generation("run_full_tests", False),
                        generation("finish", False),
                    ]
                    prefixes = [shadow(True)]
                result.append(
                    {
                        "schema_version": 3,
                        "experiment_protocol": "dev-v3",
                        "run_purpose": "comparison",
                        "experiment_id": "experiment",
                        "git_commit": "commit",
                        "task_id": task,
                        "task_class": protocol.task_class,
                        "task_role": protocol.task_role,
                        "applicable_arms": list(protocol.applicable_arms),
                        "arm": arm,
                        "repetition": repeat,
                        "execution_position": arm_order(task, repeat).index(arm) + 1,
                        "model": "fake",
                        "requested_model": "fake",
                        "reasoning_effort": "medium",
                        "docker_image_id": "sha256:image",
                        "configured_docker_image": "sandbox:dev",
                        "routing_policy": openrouter_routing_policy(),
                        "max_output_tokens": 4096,
                        "request_timeout_seconds": 60,
                        "evaluator_timeout_seconds": 30,
                        "max_file_bytes": 100000,
                        "max_total_bytes": 200000,
                        "dependency_versions": {
                            "openai": "3",
                            "mcp": "2",
                            "pydantic": "2",
                        },
                        "python_version": "3.13",
                        "platform": "test",
                        "inter_attempt_delay_seconds": 20,
                        "agent_limits": asdict(AGENT_LIMITS)
                        if arm == ARMS[3]
                        else None,
                        "configured_agent_limits": asdict(AGENT_LIMITS),
                        "success": True,
                        "evaluation_success": True,
                        "writable_paths_respected": True,
                        "protected_paths_unchanged": True,
                        "reproduction": command(),
                        "full_test": command(),
                        "lint": command(),
                        "initial_context_sha256": "a" * 64,
                        "model_calls": len(generations),
                        "tool_calls_total": int(arm != ARMS[0]),
                        "input_tokens": 80,
                        "output_tokens": 20,
                        "total_tokens": 100,
                        "reported_cost_usd": 0.001,
                        "model_latency_seconds": 1,
                        "strategy_duration_seconds": 2,
                        "fixed_evidence_duration_seconds": 0.1
                        if arm in ARMS[1:3]
                        else None,
                        "generations": generations,
                        "shadow_prefixes": prefixes,
                        "fixed_probe_executed": arm == ARMS[2],
                        "iterative_occurrence": "tool_assisted_one_patch"
                        if arm == ARMS[3]
                        else None,
                        "mutation_stages": [
                            {"mutation_applied": True, "mutation_error": None}
                            for _ in range(2 if arm == ARMS[2] else 1)
                        ],
                        "first_patch_applied": True if arm == ARMS[2] else None,
                        "second_patch_applied": True if arm == ARMS[2] else None,
                        "fixed_evidence_calls": int(arm in ARMS[1:3]),
                        "fixed_evidence": {
                            "tool": (
                                protocol.s1 if arm == ARMS[1] else protocol.s2
                            ).tool,
                            "path": (
                                protocol.s1 if arm == ARMS[1] else protocol.s2
                            ).path,
                            "kind": "pristine" if arm == ARMS[1] else "post_patch_1",
                        }
                        if arm in ARMS[1:3]
                        else None,
                        "transcript": [
                            {"tool": "apply_file_changes", "is_error": False},
                            {
                                "tool": "run_full_tests",
                                "exit_code": 0,
                                "timed_out": False,
                            },
                        ]
                        if arm == ARMS[3]
                        else [],
                    }
                )
    return result


def save(tmp_path, rows, name="input.jsonl"):
    path = tmp_path / name
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def select(rows, task="dev-011", arm=ARMS[2], repeat=1):
    return next(
        r
        for r in rows
        if r["task_id"] == task and r["arm"] == arm and r["repetition"] == repeat
    )


def test_valid_complete_shape_and_primary_results(tmp_path):
    summary = analyze_experiments(dev_v3=save(tmp_path, records()))
    experiment = summary["experiments"]["dev-v3"]
    assert summary["validation"]["valid"]
    assert experiment["attempt_count"] == 110
    assert experiment["task_count"] == 6
    assert ARMS[1] not in experiment["per_task"]["dev-015"]
    assert experiment["totals"]["successes"] == 110
    assert experiment["per_arm"][ARMS[1]]["attempts"] == 20
    assert experiment["per_arm"][ARMS[0]]["attempts"] == 30


@pytest.mark.parametrize(
    "case,reason",
    [
        ("missing", "missing attempts"),
        ("duplicate", "duplicate"),
        ("unexpected", "unexpected"),
        ("progressive_s1", "unexpected"),
        ("experiment", "mixed experiment_id"),
        ("context", "context hash drift"),
        ("prompt", "first prompt mismatch"),
        ("docker", "exit 125"),
        ("observation_docker", "exit 125"),
        ("shadow_docker", "exit 125"),
        ("schema", "schema 3"),
        ("purpose", "comparison"),
        ("config", "mixed max_output_tokens"),
        ("routing", "routing policy"),
        ("limits", "agent limits"),
        ("counterbalance", "counterbalancing"),
        ("success", "disagrees"),
        ("metric", "finite"),
    ],
)
def test_integrity_rejections(tmp_path, case, reason):
    rows = records()
    first = rows[0]
    if case == "missing":
        rows.pop()
    elif case == "duplicate":
        rows.append(deepcopy(first))
    elif case == "unexpected":
        first["arm"] = "shell"
    elif case == "progressive_s1":
        select(rows, "dev-015", ARMS[0])["arm"] = ARMS[1]
    elif case == "experiment":
        first["experiment_id"] = "another"
    elif case == "context":
        first["initial_context_sha256"] = "d" * 64
    elif case == "prompt":
        first["generations"][0]["prompt_sha256"] = "d" * 64
    elif case == "docker":
        first["reproduction"]["exit_code"] = 125
    elif case == "observation_docker":
        first["fixed_evidence"] = {"exit_code": 125}
    elif case == "shadow_docker":
        select(rows)["shadow_prefixes"][0]["full_test_exit_code"] = 125
    elif case == "schema":
        first["schema_version"] = 2
    elif case == "purpose":
        first["run_purpose"] = "smoke"
    elif case == "config":
        first["max_output_tokens"] = 10
    elif case == "routing":
        for row in rows:
            row["routing_policy"]["cross_model_fallback"] = True
    elif case == "limits":
        select(rows, arm=ARMS[3])["agent_limits"]["max_model_calls"] = 100
    elif case == "counterbalance":
        first["execution_position"] = 10
    elif case == "success":
        first["evaluation_success"] = False
    elif case == "metric":
        first["total_tokens"] = -1
    with pytest.raises(ValueError, match=reason):
        analyze_experiments(dev_v3=save(tmp_path, rows))


def test_lint_only_secondary_and_s2_mechanisms(tmp_path):
    rows = records()
    first = select(rows)
    first.update(success=False, evaluation_success=False, lint=command(1))
    first["shadow_prefixes"][-1]["evaluation_success"] = False
    first["generations"][1]["changes"] = [{"path": "module.py"}]
    summary = analyze_experiments(dev_v3=save(tmp_path, rows))
    group = summary["experiments"]["dev-v3"]["s2_mechanisms"]["dev-011"]
    assert group["successes"] == 4
    assert group["functional_tests_passed"] == 5
    assert group["lint_only_failures"] == 1
    assert group["first_patch_shadow_success"] == 0
    assert group["first_patch_shadow_failure"] == 5
    assert group["second_patch_nonempty"] == 1
    assert group["second_patch_empty"] == 4
    assert group["post_feedback_functional_recovery"] == 5
    assert group["fixed_probe_executed"] == group["second_generation"] == 5
    report = render_report(summary)
    assert "These remain evaluator failures" in report
    assert "secondary diagnostic" in report


def test_s2_does_not_fabricate_second_generation_or_missing_shadow(tmp_path):
    rows = records()
    row = select(rows)
    row.update(
        success=False,
        evaluation_success=None,
        shadow_prefixes=[],
        model_calls=1,
        fixed_probe_executed=False,
    )
    row["generations"] = row["generations"][:1]
    row["mutation_stages"] = [{"mutation_applied": False, "mutation_error": "rejected"}]
    row.update(
        first_patch_applied=False,
        second_patch_applied=False,
        fixed_evidence_calls=0,
        fixed_evidence=None,
    )
    for field in ("reproduction", "full_test", "lint"):
        row[field].update(present=False, exit_code=None, timed_out=None)
    summary = analyze_experiments(dev_v3=save(tmp_path, rows))
    group = summary["experiments"]["dev-v3"]["s2_mechanisms"]["dev-011"]
    assert group["second_generation"] == 4
    assert group["second_patch_empty"] == 4
    assert group["first_patch_shadow_missing"] == 1
    assert group["post_feedback_functional_recovery"] == 4
    assert group["mutation_rejections"] == 1


def test_agent_stored_occurrences_and_exact_sequences(tmp_path):
    rows = records()
    row = select(rows, arm=ARMS[3])
    row["iterative_occurrence"] = "feedback_responsive_iteration"
    row["shadow_prefixes"] += [{**shadow(True), "patch_index": 2}]
    row["mutation_stages"].append({"mutation_applied": True, "mutation_error": None})
    row["transcript"].append({"tool": "apply_file_changes", "is_error": False})
    summary = analyze_experiments(dev_v3=save(tmp_path, rows))
    mechanisms = summary["experiments"]["dev-v3"]["agent_overall"]
    assert mechanisms["occurrences"]["feedback_responsive_iteration"] == 1
    assert mechanisms["occurrences"]["tool_assisted_one_patch"] == 29
    assert mechanisms["multiple_mutation_attempts"] == 1
    assert mechanisms["successful_mutation_prefixes"] == 31
    assert mechanisms["tool_sequences"] == {
        "apply_file_changes → run_full_tests → finish": 29,
        "apply_file_changes → run_full_tests → apply_file_changes → finish": 1,
    }


def test_missing_telemetry_and_decimal_arithmetic(tmp_path):
    rows = records()
    first = select(rows, arm=ARMS[0])
    first["reported_cost_usd"] = None
    second = select(rows, arm=ARMS[0], repeat=2)
    second["reported_cost_usd"] = 0.000000145
    summary = analyze_experiments(dev_v3=save(tmp_path, rows))
    stats = summary["experiments"]["dev-v3"]["per_task"]["dev-011"][ARMS[0]]["metrics"]
    cost = stats["reported_cost_usd"]
    assert cost["available_count"] == 4 and cost["missing_count"] == 1
    assert Decimal(str(cost["total"])) == Decimal("0.003000145")
    assert stats["cached_input_tokens"]["total"] is None
    assert stats["cached_input_tokens"]["missing_count"] == 5
    assert (
        next(r for r in summary["attempts"] if r["arm"] == ARMS[0])[
            "cached_input_tokens"
        ]
        is None
    )


def test_matched_domain_ratios_zero_denominators_and_deltas(tmp_path):
    rows = records()
    for row in rows:
        if row["arm"] == ARMS[1]:
            row["total_tokens"] = 200
        if row["task_id"] in ("dev-015", "dev-016") and row["arm"] == ARMS[0]:
            row["total_tokens"] = 10000
        if row["task_id"] == "dev-011" and row["arm"] == ARMS[0]:
            row["reported_cost_usd"] = 0
            row.update(success=False, evaluation_success=False, reproduction=command(1))
    summary = analyze_experiments(dev_v3=save(tmp_path, rows))
    comparison = summary["experiments"]["dev-v3"]["comparisons"]["S1 / S0"]
    matched = comparison["matched_aggregate"]
    assert matched["matched_tasks"] == ["dev-011", "dev-012", "dev-013", "dev-014"]
    assert matched["numerator_attempts"] == matched["denominator_attempts"] == 20
    assert matched["ratios"]["total_tokens"] == 2
    assert comparison["per_task"]["dev-011"]["ratios"]["reported_cost_usd"] is None
    assert comparison["per_task"]["dev-011"]["success_delta_percentage_points"] == 100


def test_deterministic_safe_outputs_and_immutable_input(tmp_path):
    rows = records()
    for row in rows:
        row.update(
            prompt="SECRET_PROMPT",
            content="GENERATED_SOURCE",
            observation="SECRET_OBSERVATION",
            api_key="SECRET_KEY",
            workspace_root="C:/host/private/workspace",
        )
    path = save(tmp_path, rows)
    original = path.read_bytes()
    summary = analyze_experiments(dev_v3=path)
    second = analyze_experiments(dev_v3=path)
    assert stable_json(summary) == stable_json(second)
    assert render_report(summary) == render_report(second)
    assert render_attempts_csv(summary) == render_attempts_csv(second)
    output = tmp_path / "analysis"
    write_analysis(summary, output)
    assert {p.name for p in output.iterdir()} == {
        "summary.json",
        "report.md",
        "attempts.csv",
    }
    csv_rows = list(csv.DictReader(io.StringIO(render_attempts_csv(summary))))
    assert len(csv_rows) == 110
    assert set(csv_rows[0]) == set(CSV_FIELDS)
    for generated in output.iterdir():
        text = generated.read_text("utf-8")
        for secret in ("SECRET_", "GENERATED_SOURCE", "C:/host", "../unsafe.py"):
            assert secret not in text
    assert path.read_bytes() == original
    with pytest.raises(FileExistsError):
        write_analysis(summary, output)
    # Semantic ordering is independent of JSONL line order.
    shuffled = analyze_experiments(dev_v3=save(tmp_path, rows[::-1], "reversed.jsonl"))
    assert summary["attempts"] == shuffled["attempts"]
    assert (
        summary["experiments"]["dev-v3"]["per_task"]
        == shuffled["experiments"]["dev-v3"]["per_task"]
    )


@pytest.mark.parametrize(
    "version,schema,task",
    [("dev-v1", 1, "dev-001"), ("dev-v2", 1, "dev-005"), ("dev-v2", 2, "dev-005")],
)
def test_historical_adapters_do_not_invent_telemetry(tmp_path, version, schema, task):
    row = {
        "schema_version": schema,
        "strategy": "baseline",
        "task_id": task,
        "experiment_id": "old",
        "repetition": 1,
        "evaluation_success": True,
        "model_calls": 1,
        "tool_calls": 0,
        "duration_seconds": 2,
    }
    path = save(tmp_path, [row])
    summary = analyze_experiments(**{version.replace("-", "_"): path})
    attempt = summary["attempts"][0]
    assert attempt["arm"] == "baseline"
    assert attempt["strategy_duration_seconds"] == 2
    assert attempt["cached_input_tokens"] is None
    assert attempt["reported_cost_usd"] is None
    assert attempt["fixed_evidence_duration_seconds"] is None
    assert (
        summary["experiments"][version]["totals"]["metrics"]["total_tokens"]["total"]
        is None
    )


def test_invalid_cli_no_normal_report_and_no_overwrite(tmp_path, capsys):
    path = save(tmp_path, records()[:-1])
    output = tmp_path / "analysis"
    assert main(["--dev-v3", str(path), "--output-dir", str(output)]) == 1
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["validation"]["valid"] is False
    output.mkdir()
    with pytest.raises(SystemExit):
        main(["--dev-v3", str(path), "--output-dir", str(output)])


def test_no_inputs_rejected(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        analyze_experiments()
    with pytest.raises(SystemExit):
        main(["--output-dir", str(tmp_path / "out")])


def test_combined_versions_remain_separate_and_historical_rejection_is_normal(tmp_path):
    old = {
        "schema_version": 1,
        "strategy": "baseline",
        "task_id": "dev-001",
        "experiment_id": "old",
        "repetition": 1,
        "evaluation_success": None,
        "success": False,
        "mutation_applied": False,
    }
    inputs = {
        "dev_v1": save(tmp_path, [old], "v1.jsonl"),
        "dev_v2": save(tmp_path, [{**old, "task_id": "dev-005"}], "v2.jsonl"),
        "dev_v3": save(tmp_path, records(), "v3.jsonl"),
    }
    summary = analyze_experiments(**inputs)
    assert list(summary["experiments"]) == ["dev-v1", "dev-v2", "dev-v3"]
    assert "overall_success" not in summary
    assert summary["experiments"]["dev-v1"]["totals"]["mutation_rejections"] == 1
    assert summary["experiments"]["dev-v3"]["attempt_count"] == 110
    assert "Cross-version perspective" in render_report(summary)


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"value": NaN}'])
def test_malformed_jsonl_fails_closed(tmp_path, text):
    path = tmp_path / "bad.jsonl"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        analyze_experiments(dev_v3=path)


@pytest.mark.parametrize(
    "field",
    [
        "configured_docker_image",
        "dependency_versions",
        "python_version",
        "platform",
        "inter_attempt_delay_seconds",
    ],
)
@pytest.mark.parametrize("missing", [False, True])
def test_environment_must_be_present_and_consistent(tmp_path, field, missing):
    rows = records()
    if missing:
        rows[0].pop(field)
    else:
        rows[0][field] = (
            {"openai": "different", "mcp": "2", "pydantic": "2"}
            if field == "dependency_versions"
            else 10
            if field == "inter_attempt_delay_seconds"
            else "different"
        )
    with pytest.raises(ValueError, match=field):
        analyze_experiments(dev_v3=save(tmp_path, rows))


@pytest.mark.parametrize("arm", ARMS[1:3])
@pytest.mark.parametrize("field", ["tool", "path", "kind"])
@pytest.mark.parametrize("task", ["dev-011", "dev-013"])
def test_fixed_evidence_exact_frozen_metadata(tmp_path, arm, field, task):
    rows = records()
    select(rows, task, arm)["fixed_evidence"][field] = "incorrect"
    with pytest.raises(ValueError, match="fixed_evidence tool/path/kind"):
        analyze_experiments(dev_v3=save(tmp_path, rows))


@pytest.mark.parametrize("arm", ARMS[1:3])
def test_fixed_evidence_requires_explicit_null_path(tmp_path, arm):
    rows = records()
    select(rows, "dev-013", arm)["fixed_evidence"].pop("path")
    with pytest.raises(ValueError, match="fixed_evidence tool/path/kind"):
        analyze_experiments(dev_v3=save(tmp_path, rows))


@pytest.mark.parametrize(
    "arm,index", [(ARMS[0], 0), (ARMS[1], 0), (ARMS[2], 0), (ARMS[2], 1)]
)
def test_single_shot_and_scripted_generations_must_be_repair_batches(
    tmp_path, arm, index
):
    rows = records()
    select(rows, arm=arm)["generations"][index]["action_type"] = "run_full_tests"
    with pytest.raises(ValueError, match="repair batches"):
        analyze_experiments(dev_v3=save(tmp_path, rows))


def rejected_first(row):
    row.update(
        success=False,
        evaluation_success=None,
        model_calls=1,
        fixed_probe_executed=False,
        fixed_evidence=None,
        fixed_evidence_calls=0,
        first_patch_applied=False,
        second_patch_applied=False,
        shadow_prefixes=[],
    )
    row["generations"] = row["generations"][:1]
    row["mutation_stages"] = [{"mutation_applied": False, "mutation_error": "rejected"}]
    for field in ("reproduction", "full_test", "lint"):
        row[field].update(present=False, exit_code=None, timed_out=None)


@pytest.mark.parametrize(
    "case,reason",
    [
        ("accepted_without_second", "second generation"),
        ("two_without_probe", "fixed probe"),
        ("accepted_without_evidence", "fixed_evidence"),
        ("rejected_with_probe", "fixed probe"),
        ("rejected_with_packet", "fixed_evidence must be absent"),
        ("rejected_with_second", "second generation"),
        ("rejected_with_evaluator", "final evaluator presence"),
        ("rejected_with_commands", "final evaluator commands"),
        ("first_flag", "first_patch_applied"),
        ("second_flag", "second_patch_applied"),
    ],
)
def test_s2_lifecycle_corruption(tmp_path, case, reason):
    rows = records()
    row = select(rows)
    if case.startswith("rejected"):
        packet = deepcopy(row["fixed_evidence"])
        rejected_first(row)
        if case == "rejected_with_probe":
            row["fixed_probe_executed"] = True
        elif case == "rejected_with_packet":
            row["fixed_evidence"] = packet
        elif case == "rejected_with_second":
            row["generations"].append(generation(changes=False))
            row["model_calls"] = 2
            row["mutation_stages"].append({"mutation_applied": True})
        elif case == "rejected_with_evaluator":
            row["evaluation_success"] = False
        elif case == "rejected_with_commands":
            row["reproduction"] = command(1)
    elif case == "accepted_without_second":
        row["generations"].pop()
        row["mutation_stages"].pop()
        row["shadow_prefixes"].pop()
        row["model_calls"] = 1
    elif case == "two_without_probe":
        row["fixed_probe_executed"] = False
    elif case == "accepted_without_evidence":
        row["fixed_evidence"] = None
    elif case == "first_flag":
        row["first_patch_applied"] = False
    elif case == "second_flag":
        row["second_patch_applied"] = False
    with pytest.raises(ValueError, match=reason):
        analyze_experiments(dev_v3=save(tmp_path, rows))


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("case", ["count", "status", "error"])
def test_mutation_stages_corruption(tmp_path, arm, case):
    rows = records()
    row = select(rows, arm=arm)
    if case == "count":
        row["mutation_stages"].pop()
    elif case == "status":
        row["mutation_stages"][0]["mutation_applied"] = 1
    else:
        row["mutation_stages"][0]["mutation_error"] = "rejection on accepted stage"
    with pytest.raises(ValueError, match="mutation"):
        analyze_experiments(dev_v3=save(tmp_path, rows))


def test_agent_mutation_status_must_match_transcript(tmp_path):
    rows = records()
    row = select(rows, arm=ARMS[3])
    row["mutation_stages"][0].update(mutation_applied=False, mutation_error="rejected")
    with pytest.raises(ValueError, match="Agent mutation stages"):
        analyze_experiments(dev_v3=save(tmp_path, rows))


@pytest.mark.parametrize("arm", ARMS)
@pytest.mark.parametrize("case", ["extra", "index"])
def test_shadow_prefixes_corruption(tmp_path, arm, case):
    rows = records()
    row = select(rows, arm=arm)
    if case == "extra":
        row["shadow_prefixes"].append(
            {**shadow(True), "patch_index": len(row["shadow_prefixes"]) + 1}
        )
    elif not row["shadow_prefixes"]:
        row["shadow_prefixes"] = [{**shadow(True), "patch_index": 2}]
    else:
        row["shadow_prefixes"][0]["patch_index"] = True
    with pytest.raises(ValueError, match="shadow prefix|shadow_prefixes"):
        analyze_experiments(dev_v3=save(tmp_path, rows))


@pytest.mark.parametrize("shadow_success", [False, True])
def test_rejected_second_stage_keeps_first_accepted_shadow(tmp_path, shadow_success):
    rows = records()
    row = select(rows)
    row.update(success=False, evaluation_success=None, second_patch_applied=False)
    row["mutation_stages"][1].update(mutation_applied=False, mutation_error="rejected")
    row["shadow_prefixes"].pop()
    row["shadow_prefixes"][0] = shadow(shadow_success)
    for field in ("reproduction", "full_test", "lint"):
        row[field].update(present=False, exit_code=None, timed_out=None)
    summary = analyze_experiments(dev_v3=save(tmp_path, rows))
    assert summary["validation"]["valid"]
    row["shadow_prefixes"] = []
    with pytest.raises(ValueError, match="accepted mutation batches"):
        analyze_experiments(dev_v3=save(tmp_path, rows))


@pytest.mark.parametrize("arm", ARMS[2:])
@pytest.mark.parametrize("live_success", [False, True])
def test_final_shadow_must_match_live_evaluation(tmp_path, arm, live_success):
    rows = records()
    row = select(rows, arm=arm)
    row.update(success=live_success, evaluation_success=live_success)
    if not live_success:
        row["lint"] = command(1)
    row["shadow_prefixes"][-1] = {
        **shadow(not live_success),
        "patch_index": row["shadow_prefixes"][-1]["patch_index"],
    }
    with pytest.raises(ValueError, match="final shadow outcome disagrees"):
        analyze_experiments(dev_v3=save(tmp_path, rows))
