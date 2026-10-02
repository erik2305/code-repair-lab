"""Offline, protocol-aware analysis of immutable source-free experiment evidence."""

import csv
import io
import json
import re
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from statistics import median

from coderepair.dev_v3_experiment import AGENT_LIMITS, ARMS, TASK_PROTOCOLS, arm_order
from coderepair.openrouter_response import openrouter_routing_policy

LABELS = dict(zip(ARMS, ("S0", "S1", "S2", "Agent"), strict=True))
OCCURRENCES = (
    "none",
    "tool_assisted_one_patch",
    "context_refinement_iteration",
    "feedback_responsive_iteration",
)
METRICS = (
    "model_calls",
    "tool_calls_total",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_input_tokens",
    "reasoning_output_tokens",
    "reported_cost_usd",
    "model_latency_seconds",
    "strategy_duration_seconds",
    "fixed_evidence_duration_seconds",
)
IDENTITY_FIELDS = (
    "experiment_id",
    "git_commit",
    "requested_model",
    "model",
    "reasoning_effort",
    "docker_image_id",
    "max_output_tokens",
    "request_timeout_seconds",
    "evaluator_timeout_seconds",
    "max_file_bytes",
    "max_total_bytes",
    "routing_policy",
)
ENVIRONMENT_FIELDS = (
    "configured_docker_image",
    "docker_image_id",
    "dependency_versions",
    "python_version",
    "platform",
    "inter_attempt_delay_seconds",
)
PAIRS = ((ARMS[1], ARMS[0]), (ARMS[2], ARMS[0]), (ARMS[3], ARMS[0]), (ARMS[3], ARMS[2]))
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ACTIONS = {
    "read_file",
    "apply_file_changes",
    "run_reproduction",
    "run_full_tests",
    "run_lint",
    "finish",
}


def _plain(value):
    """Convert decimal arithmetic only at the serialization boundary."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def stable_json(value) -> str:
    return (
        json.dumps(
            _plain(value), sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2
        )
        + "\n"
    )


def _read(path: Path) -> tuple[list[dict], str]:
    # Read-only; digest identifies evidence without disclosing its physical path.
    raw = path.read_bytes()
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("JSONL input must be UTF-8") from error
    records = []
    for number, line in enumerate(lines, 1):
        try:
            record = json.loads(line, parse_float=Decimal, parse_constant=_bad_constant)
        except (ValueError, TypeError) as error:
            raise ValueError(f"invalid JSON at line {number}") from error
        if not isinstance(record, dict):
            raise ValueError(f"line {number} must contain a record object")
        records.append(record)
    if not records:
        raise ValueError("JSONL input is empty")
    return records, sha256(raw).hexdigest()


def _bad_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def _number(value, field: str):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError(f"{field} must be numeric or null")
    if not Decimal(value).is_finite() or value < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return value


def _text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    # Whitelisted identifiers must not smuggle host paths or multiline contents.
    if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", value):
        raise ValueError(f"{field} must not contain an absolute host path")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field} must be a single-line identifier")
    return value


def _passes(command) -> bool:
    return (
        isinstance(command, dict)
        and command.get("exit_code") == 0
        and command.get("timed_out") is False
    )


def _functional(record, *, shadow=False) -> bool:
    if shadow:
        return all(
            record.get(f"{name}_exit_code") == 0
            and record.get(f"{name}_timed_out") is False
            for name in ("reproduction", "full_test")
        )
    return _passes(record.get("reproduction")) and _passes(record.get("full_test"))


def _reject_infrastructure(record):
    # Exit fields only: a legitimate token count of 125 is not infrastructure.
    for key, value in record.items():
        if key.endswith("exit_code") and value == 125:
            raise ValueError("Docker exit 125: invalid infrastructure evidence")
        if isinstance(value, dict):
            _reject_infrastructure(value)
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    _reject_infrastructure(entry)


def _validate_commands(record):
    for name in ("reproduction", "full_test", "lint"):
        command = record.get(name)
        if not isinstance(command, dict):
            raise ValueError(f"{name} must contain command outcome metadata")
        for field in ("configured", "present"):
            if type(command.get(field)) is not bool:
                raise ValueError(f"{name}.{field} must be boolean")
        exit_code = command.get("exit_code")
        if exit_code is not None and type(exit_code) is not int:
            raise ValueError(f"{name}.exit_code must be integer or null")
        if (
            command.get("timed_out") is not None
            and type(command["timed_out"]) is not bool
        ):
            raise ValueError(f"{name}.timed_out must be boolean or null")
        if command["present"]:
            if not command["configured"] or type(command.get("timed_out")) is not bool:
                raise ValueError(f"{name} has inconsistent presence/timeout metadata")
            if command["timed_out"] != (exit_code is None):
                raise ValueError(f"{name} has inconsistent exit/timeout metadata")
        elif exit_code is not None or command.get("timed_out") is not None:
            raise ValueError(f"{name} absent command has execution metadata")


def _hash(value, field):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError(f"{field} must be a SHA-256 digest")


def _validate_arm_lifecycle(record, protocol):
    """Validate recorded events against the frozen arm's actual execution order."""
    arm = record["arm"]
    generations = record["generations"]
    stages = record.get("mutation_stages")
    if not isinstance(stages, list) or any(
        not isinstance(stage, dict) or type(stage.get("mutation_applied")) is not bool
        for stage in stages
    ):
        raise ValueError("mutation_stages must contain boolean mutation statuses")
    for stage in stages:
        error = stage.get("mutation_error")
        if stage["mutation_applied"]:
            if error is not None:
                raise ValueError("accepted mutation stage must not contain an error")
        elif not isinstance(error, str) or not error.strip():
            raise ValueError("rejected mutation stage must contain an error")

    if arm == ARMS[3]:
        transcript = record.get("transcript")
        if not isinstance(transcript, list) or any(
            not isinstance(entry, dict) for entry in transcript
        ):
            raise ValueError("Agent transcript must contain tool metadata")
        mutations = [
            entry for entry in transcript if entry.get("tool") == "apply_file_changes"
        ]
        if len(stages) != len(mutations) or any(
            type(entry.get("is_error")) is not bool
            or stage["mutation_applied"] != (not entry["is_error"])
            for stage, entry in zip(stages, mutations, strict=False)
        ):
            raise ValueError("Agent mutation stages disagree with executed mutations")
    else:
        if any(
            generation["action_type"] != "apply_file_changes"
            for generation in generations
        ):
            raise ValueError(
                "S0/S1/S2 generations must be apply_file_changes repair batches"
            )
        if len(stages) != len(generations):
            raise ValueError("mutation_stages count must match repair generations")
        accepted = all(stage["mutation_applied"] for stage in stages)
        if (record.get("evaluation_success") is not None) != accepted:
            raise ValueError("final evaluator presence disagrees with mutation stages")
        if not accepted and any(
            record[name]["present"] for name in ("reproduction", "full_test", "lint")
        ):
            raise ValueError("rejected mutation must not have final evaluator commands")

    evidence = record.get("fixed_evidence")
    probe = None
    kind = None
    if arm == ARMS[1]:
        probe, kind = protocol.s1, "pristine"
    elif arm == ARMS[2]:
        first_accepted = stages[0]["mutation_applied"]
        if len(generations) != (2 if first_accepted else 1):
            raise ValueError(
                "S2 first mutation status requires matching second generation"
            )
        if (
            type(record.get("fixed_probe_executed")) is not bool
            or record["fixed_probe_executed"] != first_accepted
        ):
            raise ValueError("S2 fixed probe execution disagrees with first mutation")
        for field, expected in (
            ("first_patch_applied", first_accepted),
            (
                "second_patch_applied",
                stages[1]["mutation_applied"] if len(stages) == 2 else False,
            ),
        ):
            if type(record.get(field)) is not bool or record[field] != expected:
                raise ValueError(f"S2 {field} disagrees with mutation stages")
        if first_accepted:
            probe, kind = protocol.s2, "post_patch_1"
    if probe is not None:
        if not isinstance(evidence, dict) or any(
            field not in evidence or evidence[field] != expected
            for field, expected in (
                ("tool", probe.tool),
                ("path", probe.path),
                ("kind", kind),
            )
        ):
            raise ValueError("fixed_evidence tool/path/kind differs from frozen probe")
    elif evidence is not None:
        raise ValueError("fixed_evidence must be absent when no fixed probe runs")
    if type(record.get("fixed_evidence_calls")) is not int or record[
        "fixed_evidence_calls"
    ] != int(probe is not None):
        raise ValueError("fixed evidence count disagrees with frozen arm lifecycle")

    expected_prefixes = (
        sum(stage["mutation_applied"] for stage in stages) if arm in ARMS[2:] else 0
    )
    if len(record["shadow_prefixes"]) != expected_prefixes:
        raise ValueError(
            "shadow_prefixes count disagrees with accepted mutation batches"
        )


def _validate_v3(records):
    expected = {
        (task, repeat, arm)
        for task, protocol in TASK_PROTOCOLS.items()
        for repeat in range(1, 6)
        for arm in protocol.applicable_arms
    }
    indexed = {}
    for record in records:
        if (
            type(record.get("schema_version")) is not int
            or record["schema_version"] != 3
            or record.get("experiment_protocol") != "dev-v3"
            or record.get("run_purpose") != "comparison"
        ):
            raise ValueError(
                "DEV-v3 requires schema 3, dev-v3 protocol, comparison purpose"
            )
        task, repeat, arm = (record.get(k) for k in ("task_id", "repetition", "arm"))
        if (
            not isinstance(task, str)
            or not isinstance(arm, str)
            or type(repeat) is not int
            or (task, repeat, arm) not in expected
        ):
            raise ValueError(
                "unexpected task/repetition/arm (including progressive S1)"
            )
        key = (task, repeat, arm)
        if key in indexed:
            raise ValueError("duplicate task/repetition/arm")
        indexed[key] = record
        protocol = TASK_PROTOCOLS[task]
        if (
            record.get("task_class") != protocol.task_class
            or record.get("task_role") != protocol.task_role
            or record.get("applicable_arms") != list(protocol.applicable_arms)
        ):
            raise ValueError(
                "task role/class/applicability does not match frozen mapping"
            )
        if record.get("execution_position") != arm_order(task, repeat).index(arm) + 1:
            raise ValueError("execution position violates frozen counterbalancing")
        _hash(record.get("initial_context_sha256"), "initial_context_sha256")
        _reject_infrastructure(record)
        _validate_commands(record)
        if type(record.get("success")) is not bool:
            raise ValueError("success must be boolean")
        evaluation = record.get("evaluation_success")
        if evaluation is not None and type(evaluation) is not bool:
            raise ValueError("evaluation_success must be boolean or null")
        if record["success"] != (evaluation is True):
            raise ValueError("success disagrees with independent evaluator outcome")
        if record["success"] and not (
            record.get("writable_paths_respected") is True
            and record.get("protected_paths_unchanged") is True
            and _functional(record)
            and (not record["lint"]["configured"] or _passes(record["lint"]))
        ):
            raise ValueError(
                "successful evaluation has inconsistent policy/command outcomes"
            )
        generations = record.get("generations")
        if not isinstance(generations, list) or not generations:
            raise ValueError("generations must be a non-empty list")
        for generation in generations:
            if not isinstance(generation, dict):
                raise ValueError("generation must be an object")
            _hash(generation.get("prompt_sha256"), "prompt_sha256")
            if generation.get("action_type") not in _ACTIONS:
                raise ValueError("unknown generation action_type")
            if not isinstance(generation.get("changes"), list):
                raise ValueError("generation changes must be a list")
        if type(record.get("model_calls")) is not int or record["model_calls"] != len(
            generations
        ):
            raise ValueError("model_calls disagrees with generation count")
        if (
            arm in ARMS[:2]
            and len(generations) != 1
            or arm == ARMS[2]
            and len(generations) > 2
        ):
            raise ValueError("generation count violates arm contract")
        for metric in METRICS:
            _number(record.get(metric), metric)
            if ("tokens" in metric or "calls" in metric) and record.get(
                metric
            ) is not None:
                if type(record[metric]) is not int:
                    raise ValueError(f"{metric} must be integer or null")
        if arm == ARMS[3]:
            if record.get("agent_limits") != asdict(AGENT_LIMITS):
                raise ValueError("agent limits differ from frozen protocol")
            if record.get("iterative_occurrence") not in OCCURRENCES:
                raise ValueError("unknown stored iterative occurrence")
        if record.get("configured_agent_limits") is not None:
            if record["configured_agent_limits"] != asdict(AGENT_LIMITS):
                raise ValueError("configured agent limits differ from frozen protocol")
        shadows = record.get("shadow_prefixes")
        if not isinstance(shadows, list) or any(
            not isinstance(p, dict) for p in shadows
        ):
            raise ValueError("shadow_prefixes must be a list of measurements")
        for index, prefix in enumerate(shadows, 1):
            if (
                type(prefix.get("patch_index")) is not int
                or prefix["patch_index"] != index
                or type(prefix.get("evaluation_success")) is not bool
            ):
                raise ValueError("invalid shadow prefix measurement")
        _validate_arm_lifecycle(record, protocol)
        if (
            evaluation is not None
            and shadows
            and shadows[-1]["evaluation_success"] != evaluation
        ):
            raise ValueError("final shadow outcome disagrees with live evaluation")
    if set(indexed) != expected:
        raise ValueError(f"missing attempts: expected 110, found {len(indexed)}")
    for field in dict.fromkeys((*IDENTITY_FIELDS, *ENVIRONMENT_FIELDS)):
        if any(field not in row or row[field] is None for row in records):
            raise ValueError(f"missing required identity/configuration: {field}")
        if len({stable_json(row[field]) for row in records}) != 1:
            raise ValueError(f"mixed {field} across comparison")
    for field in (
        "experiment_id",
        "git_commit",
        "requested_model",
        "model",
        "reasoning_effort",
        "docker_image_id",
    ):
        _text(records[0][field], field)
    if records[0]["model"] != records[0]["requested_model"]:
        raise ValueError("requested model does not match configured model")
    if records[0]["routing_policy"] != openrouter_routing_policy():
        raise ValueError("routing policy differs from frozen OpenRouter policy")
    if any(type(value) is not bool for value in records[0]["routing_policy"].values()):
        raise ValueError("routing policy values must be boolean")
    for field in ("max_output_tokens", "max_file_bytes", "max_total_bytes"):
        if type(records[0][field]) is not int or records[0][field] <= 0:
            raise ValueError(f"{field} must be a positive integer")
    for field in ("request_timeout_seconds", "evaluator_timeout_seconds"):
        if _number(records[0][field], field) <= 0:
            raise ValueError(f"{field} must be positive")
    if records[0]["max_total_bytes"] < records[0]["max_file_bytes"]:
        raise ValueError("invalid context byte budget relation")
    for record in records:
        for field in ENVIRONMENT_FIELDS[:2] + ("python_version", "platform"):
            _text(record.get(field), field)
        versions = record.get("dependency_versions")
        if not isinstance(versions, dict) or set(versions) != {
            "openai",
            "mcp",
            "pydantic",
        }:
            raise ValueError("invalid dependency version provenance")
        for package, version in versions.items():
            _text(version, package)
        _number(record.get("inter_attempt_delay_seconds"), "inter-attempt delay")
    for task in TASK_PROTOCOLS:
        if (
            len({r["initial_context_sha256"] for r in records if r["task_id"] == task})
            != 1
        ):
            raise ValueError(f"initial context hash drift for {task}")
        for repeat in range(1, 6):
            first = indexed[task, repeat, ARMS[0]]["generations"][0]
            second = indexed[task, repeat, ARMS[2]]["generations"][0]
            if first["prompt_sha256"] != second["prompt_sha256"]:
                raise ValueError(
                    f"S0/S2 first prompt mismatch for {task} repetition {repeat}"
                )


def _normalize(record, version):
    """Explicit whitelist: never propagate source, prompts, paths or observations."""
    v3 = version == "dev-v3"
    row = {
        key: record.get(key)
        for key in (
            "experiment_id",
            "task_id",
            "task_class",
            "task_role",
            "repetition",
            "git_commit",
            "docker_image_id",
            "iterative_occurrence",
        )
    }
    row.update(
        experiment=version,
        arm=record["arm"] if v3 else record["strategy"],
        success=record.get("evaluation_success") is True,
    )
    for key in ("experiment_id", "task_id", "git_commit", "docker_image_id"):
        if row[key] is not None:
            _text(row[key], key)
    for metric in METRICS:
        # Schema 1/2 duration_seconds is the same measured live strategy duration.
        source = {
            "tool_calls_total": "tool_calls",
            "strategy_duration_seconds": "duration_seconds",
        }.get(metric, metric)
        row[metric] = _number(record.get(metric if v3 else source), metric)
    row["functional_tests_passed"] = (
        _functional(record)
        if "reproduction" in record and "full_test" in record
        else None
    )
    lint = record.get("lint")
    row["lint_failed"] = bool(
        isinstance(lint, dict)
        and lint.get("configured") is True
        and lint.get("present") is True
        and not _passes(lint)
    )
    row["lint_only_failure"] = bool(
        not row["success"]
        and row["functional_tests_passed"]
        and isinstance(lint, dict)
        and lint.get("configured") is True
        and lint.get("present") is True
        and not _passes(lint)
    )
    generations = record.get("generations", [])
    row["returned_model"] = sorted(
        {
            _text(g["returned_model"], "returned_model")
            for g in generations
            if g.get("returned_model") is not None
        }
        | (
            {_text(record["returned_model"], "returned_model")}
            if record.get("returned_model") is not None
            else set()
        )
    )
    row["routed_provider"] = sorted(
        {
            _text(g["routed_provider"], "routed_provider")
            for g in generations
            if g.get("routed_provider") is not None
        }
        | (
            {_text(record["routed_provider"], "routed_provider")}
            if record.get("routed_provider") is not None
            else set()
        )
    )
    # Action names only; raw proposal paths and message text are never exported.
    sequence = [g.get("action_type") for g in generations]
    if row["arm"] in ("agent", ARMS[3]):
        sequence = [entry.get("tool") for entry in record.get("transcript", [])]
        if generations and generations[-1].get("action_type") == "finish":
            sequence.append("finish")
    if any(action not in _ACTIONS for action in sequence):
        raise ValueError("unknown source-free action/tool in sequence")
    row["tool_sequence"] = sequence
    shadows = record.get("shadow_prefixes", [])
    row["mutation_prefixes"] = len(shadows) if "shadow_prefixes" in record else None
    row["first_patch_shadow_success"] = (
        shadows[0]["evaluation_success"] if shadows else None
    )
    row["first_patch_functional_success"] = (
        _functional(shadows[0], shadow=True) if shadows else None
    )
    row["fixed_probe_executed"] = record.get("fixed_probe_executed")
    row["second_generation"] = (
        len(generations) > 1 if v3 and row["arm"] == ARMS[2] else None
    )
    row["second_patch_nonempty"] = (
        bool(generations[1]["changes"]) if row["second_generation"] else None
    )
    row["execution_timeouts"] = sum(
        command.get("timed_out") is True
        for command in (
            record.get("reproduction", {}),
            record.get("full_test", {}),
            record.get("lint", {}),
            record.get("fixed_evidence") or {},
            *record.get("transcript", []),
        )
    )
    row["mutation_rejections"] = (
        sum(
            stage["mutation_applied"] is False
            for stage in record.get("mutation_stages", [])
        )
        if v3
        else int(record.get("mutation_applied") is False)
        if row["arm"] == "baseline"
        else sum(
            entry.get("tool") == "apply_file_changes" and entry.get("is_error") is True
            for entry in record.get("transcript", [])
        )
    )
    return row


def _historical(path, version, tasks):
    records, digest = _read(path)
    for record in records:
        if type(record.get("schema_version")) is not int or record[
            "schema_version"
        ] not in (1, 2):
            raise ValueError(
                f"{version} supports inspected historical schemas 1 and 2 only"
            )
        if record.get("task_id") not in tasks or record.get("strategy") not in (
            "baseline",
            "agent",
        ):
            raise ValueError(f"unexpected historical task/strategy for {version}")
        if "evaluation_success" not in record or (
            record["evaluation_success"] is not None
            and type(record["evaluation_success"]) is not bool
        ):
            raise ValueError("historical evaluation_success must be boolean or null")
        if "success" in record and (
            type(record["success"]) is not bool
            or record["success"] != (record["evaluation_success"] is True)
        ):
            raise ValueError("historical success disagrees with evaluator outcome")
        if type(record.get("repetition")) is not int or record["repetition"] < 1:
            raise ValueError("historical repetition must be a positive integer")
        _reject_infrastructure(record)
    return records, digest


def load_dev_v1(path: Path):
    return _historical(path, "dev-v1", {f"dev-{i:03}" for i in range(1, 5)})


def load_dev_v2(path: Path):
    return _historical(path, "dev-v2", {f"dev-{i:03}" for i in range(5, 11)})


def load_dev_v3(path: Path):
    records, digest = _read(path)
    _validate_v3(records)
    return records, digest


def metric_statistics(values):
    available = [Decimal(value) for value in values if value is not None]
    return {
        "available_count": len(available),
        "missing_count": len(values) - len(available),
        "total": sum(available) if available else None,
        "mean": sum(available) / len(available) if available else None,
        "median": median(available) if available else None,
        "min": min(available) if available else None,
        "max": max(available) if available else None,
    }


def _group(rows):
    return {
        "attempts": len(rows),
        "successes": sum(r["success"] for r in rows),
        "success_rate_percent": Decimal(100)
        * sum(r["success"] for r in rows)
        / len(rows),
        "functional_tests_passed": sum(
            r["functional_tests_passed"] is True for r in rows
        ),
        "evaluator_failures": sum(not r["success"] for r in rows),
        "lint_only_failures": sum(r["lint_only_failure"] for r in rows),
        "lint_failures": sum(r["lint_failed"] for r in rows),
        "execution_timeouts": sum(r["execution_timeouts"] for r in rows),
        "mutation_rejections": sum(r["mutation_rejections"] for r in rows),
        "metrics": {
            metric: metric_statistics([r[metric] for r in rows]) for metric in METRICS
        },
    }


def _s2(rows):
    result = _group(rows)
    result.update(
        first_patch_shadow_success=sum(
            r["first_patch_shadow_success"] is True for r in rows
        ),
        first_patch_shadow_failure=sum(
            r["first_patch_shadow_success"] is False for r in rows
        ),
        first_patch_shadow_missing=sum(
            r["first_patch_shadow_success"] is None for r in rows
        ),
        fixed_probe_executed=sum(r["fixed_probe_executed"] is True for r in rows),
        second_generation=sum(r["second_generation"] is True for r in rows),
        second_patch_nonempty=sum(r["second_patch_nonempty"] is True for r in rows),
        second_patch_empty=sum(r["second_patch_nonempty"] is False for r in rows),
        post_feedback_functional_recovery=sum(
            r["first_patch_functional_success"] is False
            and r["functional_tests_passed"] is True
            for r in rows
        ),
    )
    return result


def _agent(rows):
    return {
        "occurrences": {
            name: sum(r["iterative_occurrence"] == name for r in rows)
            for name in OCCURRENCES
        },
        "successful_mutation_prefixes": sum(r["mutation_prefixes"] or 0 for r in rows),
        "first_patch_shadow_success": sum(
            r["first_patch_shadow_success"] is True for r in rows
        ),
        "first_patch_shadow_missing": sum(
            r["first_patch_shadow_success"] is None for r in rows
        ),
        "multiple_mutation_attempts": sum(
            (r["mutation_prefixes"] or 0) > 1 for r in rows
        ),
        "tool_sequences": dict(
            sorted(Counter(" → ".join(r["tool_sequence"]) for r in rows).items())
        ),
    }


def _ratio(numerator, denominator, metric):
    left, right = ([r[metric] for r in rows] for rows in (numerator, denominator))
    # Missing telemetry is not zero, and incomplete-domain ratios are not invented.
    if not left or not right or None in left or None in right:
        return None
    num = sum(map(Decimal, left)) / len(left)
    den = sum(map(Decimal, right)) / len(right)
    return num / den if den else None


def _comparisons(rows):
    comparisons = {}
    for numerator, denominator in PAIRS:
        tasks = sorted(
            {r["task_id"] for r in rows if r["arm"] == numerator}
            & {r["task_id"] for r in rows if r["arm"] == denominator}
        )

        def compare(domain):
            left = [r for r in rows if r["task_id"] in domain and r["arm"] == numerator]
            right = [
                r for r in rows if r["task_id"] in domain and r["arm"] == denominator
            ]
            return {
                "matched_tasks": domain,
                "numerator_attempts": len(left),
                "denominator_attempts": len(right),
                "ratios": {
                    m: _ratio(left, right, m)
                    for m in (
                        "total_tokens",
                        "reported_cost_usd",
                        "model_calls",
                        "strategy_duration_seconds",
                    )
                },
                "success_delta_percentage_points": (
                    _group(left)["success_rate_percent"]
                    - _group(right)["success_rate_percent"]
                ),
            }

        comparisons[f"{LABELS[numerator]} / {LABELS[denominator]}"] = {
            "per_task": {task: compare([task]) for task in tasks},
            "matched_aggregate": compare(tasks),
        }
    return comparisons


def analyze_experiments(
    *,
    dev_v1: Path | None = None,
    dev_v2: Path | None = None,
    dev_v3: Path | None = None,
) -> dict:
    """Validate explicit inputs and return whitelisted deterministic analysis."""
    if dev_v1 is None and dev_v2 is None and dev_v3 is None:
        raise ValueError("at least one explicit experiment input is required")
    experiments, attempts, warnings = {}, [], []
    for version, path, loader in (
        ("dev-v1", dev_v1, load_dev_v1),
        ("dev-v2", dev_v2, load_dev_v2),
        ("dev-v3", dev_v3, load_dev_v3),
    ):
        if path is None:
            continue
        records, digest = loader(path)
        rows = [_normalize(record, version) for record in records]
        arms = ARMS if version == "dev-v3" else ("baseline", "agent")
        rows.sort(key=lambda r: (r["task_id"], arms.index(r["arm"]), r["repetition"]))
        tasks = sorted({r["task_id"] for r in rows})
        experiment = {
            "input_sha256": digest,
            "schemas": sorted({r["schema_version"] for r in records}),
            "task_count": len(tasks),
            "attempt_count": len(rows),
            "experiment_ids": sorted({r["experiment_id"] for r in rows}),
            "per_task": {
                task: {
                    arm: _group(
                        [r for r in rows if r["task_id"] == task and r["arm"] == arm]
                    )
                    for arm in arms
                    if any(r["task_id"] == task and r["arm"] == arm for r in rows)
                }
                for task in tasks
            },
            "per_arm": {
                arm: _group([r for r in rows if r["arm"] == arm])
                for arm in arms
                if any(r["arm"] == arm for r in rows)
            },
            "totals": _group(rows),
            "returned_models": sorted(
                {model for row in rows for model in row["returned_model"]}
            ),
            "routed_providers": sorted(
                {provider for row in rows for provider in row["routed_provider"]}
            ),
        }
        if version == "dev-v3":
            experiment.update(
                configuration={key: records[0][key] for key in IDENTITY_FIELDS},
                configured_agent_limits=asdict(AGENT_LIMITS),
                environment={
                    key: [
                        json.loads(value)
                        for value in sorted(
                            {stable_json(r.get(key)).strip() for r in records}
                        )
                    ]
                    for key in ENVIRONMENT_FIELDS
                },
                task_roles={
                    task: {
                        "task_class": TASK_PROTOCOLS[task].task_class,
                        "task_role": TASK_PROTOCOLS[task].task_role,
                    }
                    for task in tasks
                },
                s2_mechanisms={
                    task: _s2(
                        [
                            r
                            for r in rows
                            if r["task_id"] == task and r["arm"] == ARMS[2]
                        ]
                    )
                    for task in tasks
                },
                agent_mechanisms={
                    task: _agent(
                        [
                            r
                            for r in rows
                            if r["task_id"] == task and r["arm"] == ARMS[3]
                        ]
                    )
                    for task in tasks
                },
                agent_overall=_agent([r for r in rows if r["arm"] == ARMS[3]]),
                comparisons=_comparisons(rows),
            )
        else:
            warnings.append(
                f"{version}: unrecorded historical telemetry remains null; "
                "no pooled solve rate"
            )
        for metric in METRICS:
            if experiment["totals"]["metrics"][metric]["missing_count"]:
                warnings.append(f"{version}: missing telemetry for {metric}")
        experiments[version] = experiment
        attempts.extend(rows)
    return _plain(
        {
            "validation": {"valid": True, "errors": [], "warnings": warnings},
            "experiments": experiments,
            "attempts": attempts,
        }
    )


def _cell(group):
    if group is None:
        return "N/A"
    return (
        f"{group['successes']}/{group['attempts']} "
        f"({group['success_rate_percent']:.1f}%)"
    )


def _table(headers, rows):
    # Prevent identifiers/action metadata from introducing Markdown structure.
    def safe(value):
        if value is None:
            return "null"
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *["| " + " | ".join(map(safe, row)) + " |" for row in rows],
        "",
    ]


def render_report(summary: dict) -> str:
    """Deterministic, descriptive templates; no model-written interpretation."""
    if summary["validation"]["valid"] is not True:
        raise ValueError("cannot render research report for invalid evidence")
    lines = [
        "# CodeRepair Lab experiment analysis",
        "",
        "Task is the primary analysis unit. This is a synthetic mechanism-study pilot,",
        "not evidence of universal strategy superiority. Five repetitions do not",
        "support inferential claims. Solve rates are not pooled across versions.",
        "",
        "Functional-test success is a secondary diagnostic and does not replace the",
        "preregistered evaluator-success outcome. Reproduction and full-suite must",
        "exit 0 without timeout; lint is excluded. Lint-only failures stay failures.",
        "",
    ]
    for version, experiment in summary["experiments"].items():
        lines.extend(
            [
                f"## {version.upper()}",
                "",
                f"Validated attempts: {experiment['attempt_count']}; "
                f"tasks: {experiment['task_count']}.",
                "",
                "### Primary independent evaluator outcomes",
                "",
            ]
        )
        arms = ARMS if version == "dev-v3" else ("baseline", "agent")
        labels = [LABELS[a] if version == "dev-v3" else a for a in arms]
        lines.extend(
            _table(
                ["Task", *labels],
                [
                    [task, *[_cell(groups.get(arm)) for arm in arms]]
                    for task, groups in experiment["per_task"].items()
                ],
            )
        )
        lines.extend(["### Functional-test and lint diagnostics", ""])
        lines.extend(
            _table(
                [
                    "Task",
                    "Arm",
                    "Functional pass",
                    "Evaluator failures",
                    "Lint-only failures",
                ],
                [
                    [
                        task,
                        LABELS.get(arm, arm),
                        group["functional_tests_passed"],
                        group["evaluator_failures"],
                        group["lint_only_failures"],
                    ]
                    for task, groups in experiment["per_task"].items()
                    for arm, group in groups.items()
                ],
            )
        )
        lines.extend(
            [
                "### Resource measurements",
                "",
                "Arm aggregates are descriptive telemetry; applicability sets differ.",
                "Each metric reports available/missing counts; missing is not zero.",
                "",
            ]
        )
        lines.extend(
            _table(
                [
                    "Domain",
                    "Arm",
                    "Metric",
                    "Available",
                    "Missing",
                    "Total",
                    "Mean",
                    "Median",
                    "Min",
                    "Max",
                ],
                [
                    [
                        domain,
                        LABELS.get(arm, arm),
                        metric,
                        *[
                            stats[key]
                            for key in (
                                "available_count",
                                "missing_count",
                                "total",
                                "mean",
                                "median",
                                "min",
                                "max",
                            )
                        ],
                    ]
                    for domain, groups in [
                        ("all applicable tasks", experiment["per_arm"]),
                        *experiment["per_task"].items(),
                    ]
                    for arm, group in groups.items()
                    for metric, stats in group["metrics"].items()
                ],
            )
        )
        if version != "dev-v3":
            lines.extend(
                [
                    "Historical baseline/agent terminology is retained. "
                    "Unrecorded telemetry is null.",
                    "",
                ]
            )
            continue
        lines.extend(
            [
                "### Run identity and environment",
                "",
                "```json",
                stable_json(
                    {
                        key: experiment[key]
                        for key in (
                            "configuration",
                            "configured_agent_limits",
                            "environment",
                            "returned_models",
                            "routed_providers",
                        )
                    }
                ).rstrip(),
                "```",
                "",
                "### S2 mechanism measurements",
                "",
            ]
        )
        s2_fields = (
            "attempts",
            "successes",
            "functional_tests_passed",
            "first_patch_shadow_success",
            "first_patch_shadow_failure",
            "first_patch_shadow_missing",
            "fixed_probe_executed",
            "second_generation",
            "second_patch_nonempty",
            "second_patch_empty",
            "lint_only_failures",
            "post_feedback_functional_recovery",
        )
        lines.extend(
            _table(
                ["Task", *s2_fields],
                [
                    [task, *[group[key] for key in s2_fields]]
                    for task, group in experiment["s2_mechanisms"].items()
                ],
            )
        )
        lines.extend(
            [
                "Recovery describes an observed transition, not causal necessity.",
                "",
                "### Agent occurrence and mutation prefixes",
                "",
            ]
        )
        lines.extend(
            _table(
                [
                    "Task",
                    *OCCURRENCES,
                    "Mutation prefixes",
                    "First prefix passed",
                    "Multiple mutations",
                ],
                [
                    [
                        task,
                        *[group["occurrences"][key] for key in OCCURRENCES],
                        group["successful_mutation_prefixes"],
                        group["first_patch_shadow_success"],
                        group["multiple_mutation_attempts"],
                    ]
                    for task, group in [
                        *experiment["agent_mechanisms"].items(),
                        ("overall", experiment["agent_overall"]),
                    ]
                ],
            )
        )
        lines.extend(
            [
                "Tool use before one correct patch is not repair after a failed patch.",
                "Occurrence labels retain the historical classifier: different patch "
                "batches mean distinct hashes of sorted paths/content digests, "
                "not a semantic materiality judgment. Aggregate Agent resource "
                "ratios measure agentic interaction overhead, not pure iteration cost.",
                "",
            ]
        )
        lines.extend(
            _table(
                ["Task", "Exact action sequence", "Count"],
                [
                    [task, sequence, count]
                    for task, group in experiment["agent_mechanisms"].items()
                    for sequence, count in group["tool_sequences"].items()
                ],
            )
        )
        lines.extend(
            [
                "### Matched-task resource ratios and success deltas",
                "",
                "Ratios use mean per-attempt resources on matched task domains only;",
                "Missing telemetry or zero denominators produce null. "
                "Deltas are percentage points.",
                "",
            ]
        )
        lines.extend(
            _table(
                [
                    "Comparison",
                    "Domain",
                    "Tokens",
                    "Cost",
                    "Model calls",
                    "Duration",
                    "Success delta (pp)",
                ],
                [
                    [
                        name,
                        domain,
                        *[
                            item["ratios"][key]
                            for key in (
                                "total_tokens",
                                "reported_cost_usd",
                                "model_calls",
                                "strategy_duration_seconds",
                            )
                        ],
                        item["success_delta_percentage_points"],
                    ]
                    for name, comparison in experiment["comparisons"].items()
                    for domain, item in [
                        *comparison["per_task"].items(),
                        (
                            ", ".join(comparison["matched_aggregate"]["matched_tasks"]),
                            comparison["matched_aggregate"],
                        ),
                    ]
                ],
            )
        )
        lines.extend(["### Findings", ""])
        for task, groups in experiment["per_task"].items():
            lines.append(
                f"On {task}, "
                + "; ".join(
                    f"{LABELS[arm]} succeeded {_cell(group)}"
                    for arm, group in groups.items()
                )
                + "."
            )
            s2 = experiment["s2_mechanisms"][task]
            if s2["lint_only_failures"]:
                lines.append(
                    f"S2 functional passes: "
                    f"{s2['functional_tests_passed']}/{s2['attempts']}; "
                    f"{s2['lint_only_failures']} final states failed lint. "
                    "These remain evaluator failures."
                )
                if task == "dev-013":
                    lines.append(
                        "The exact lint causes are not recoverable from the "
                        "source-free canonical records, which retain outcomes "
                        "but not lint messages or generated source."
                    )
        lines.extend(["", "### Positive/negative controls", ""])
        for positive, negative in (("dev-011", "dev-012"), ("dev-013", "dev-014")):
            lines.append(f"#### {positive} versus {negative}")
            lines.append("")
            for task in (positive, negative):
                groups = experiment["per_task"][task]
                s2 = experiment["s2_mechanisms"][task]
                agent = experiment["agent_mechanisms"][task]
                role = experiment["task_roles"][task]
                lines.append(
                    f"{task} ({role['task_class']}, {role['task_role']}): "
                    f"S0 {_cell(groups[ARMS[0]])}; S1 {_cell(groups[ARMS[1]])}; "
                    f"S2 {_cell(groups[ARMS[2]])}; "
                    f"Agent {_cell(groups[ARMS[3]])}; "
                    f"S2 first shadow passed "
                    f"{s2['first_patch_shadow_success']}/{s2['attempts']}; "
                    f"Agent first shadow passed "
                    f"{agent['first_patch_shadow_success']}/5."
                )
                if task == "dev-013":
                    sequences = [
                        row["tool_sequence"]
                        for row in summary["attempts"]
                        if row["experiment"] == version
                        and row["task_id"] == task
                        and row["arm"] == ARMS[3]
                    ]
                    before_patch = [
                        sequence[: sequence.index("apply_file_changes")]
                        for sequence in sequences
                        if "apply_file_changes" in sequence
                    ]
                    reads_without_execution = sum(
                        "read_file" in prefix
                        and not any(
                            tool in prefix
                            for tool in (
                                "run_reproduction", "run_full_tests", "run_lint"
                            )
                        )
                        for prefix in before_patch
                    )
                    lines.append(
                        "The frozen role is runtime-diagnostic positive, but "
                        f"{reads_without_execution}/{len(sequences)} Agent traces "
                        "read context before the first mutation without preceding "
                        "execution feedback. Intended task role is not the exhibited "
                        "Agent mechanism; success does not establish that runtime "
                        "diagnostics were required."
                    )
                if groups[ARMS[1]]["successes"] > groups[ARMS[0]]["successes"]:
                    lines.append(
                        "Fixed evidence coincided with more primary successes; "
                        "this is consistent with useful information, "
                        "not proof of causality."
                    )
                elif groups[ARMS[0]]["successes"] == 5:
                    lines.append(
                        "S0 already passed all repetitions; extra fixed evidence "
                        "did not increase the primary outcome."
                    )
                for name in ("S1 / S0", "S2 / S0", "Agent / S0"):
                    overhead = experiment["comparisons"][name]["per_task"][task][
                        "ratios"
                    ]
                    lines.append(
                        f"Resource ratios {name}: tokens {overhead['total_tokens']}, "
                        f"cost {overhead['reported_cost_usd']}, "
                        f"model calls {overhead['model_calls']}, "
                        f"duration {overhead['strategy_duration_seconds']}."
                    )
                lines.append("")
        lines.extend(["### Progressive feedback", ""])
        for task in ("dev-015", "dev-016"):
            s2 = experiment["s2_mechanisms"][task]
            groups = experiment["per_task"][task]
            lines.append(
                f"{task}: S0 {_cell(groups[ARMS[0]])}; S2 {_cell(groups[ARMS[2]])}; "
                f"Agent {_cell(groups[ARMS[3]])}. S2 first shadows passed "
                f"{s2['first_patch_shadow_success']}/{s2['attempts']}; "
                f"post-feedback functional recoveries: "
                f"{s2['post_feedback_functional_recovery']}."
            )
            lines.append(
                "Stored Agent occurrences: "
                + json.dumps(
                    experiment["agent_mechanisms"][task]["occurrences"], sort_keys=True
                )
                + "."
            )
            overhead = experiment["comparisons"]["Agent / S2"]["per_task"][task][
                "ratios"
            ]
            lines.append(
                f"Agent/S2 ratios: tokens {overhead['total_tokens']}, "
                f"cost {overhead['reported_cost_usd']}, "
                f"model calls {overhead['model_calls']}."
            )
            if s2["post_feedback_functional_recovery"]:
                lines.append(
                    "Functional improvement followed post-attempt feedback; "
                    "the full-test probe exposed F2 information withheld from "
                    "the initial context. These tasks mix feedback timing with "
                    "information availability, as anticipated in the preregistration; "
                    "they do not isolate feedback alone or establish necessity."
                )
            if groups[ARMS[2]]["successes"] == groups[ARMS[3]]["successes"] == 5:
                lines.append(
                    "S2 and Agent both passed all repetitions. S2 received a "
                    "preregistered designer-selected task-specific probe, whereas "
                    "Agent chose tools adaptively. Equal final success here does "
                    "not establish that autonomous evidence selection is "
                    "unnecessary in general."
                )
            lines.append("")
        ratio = experiment["comparisons"]["Agent / S2"]["matched_aggregate"]["ratios"][
            "total_tokens"
        ]
        if ratio is not None:
            lines.extend(
                [
                    f"Agent used {ratio:.2f}× as many tokens per attempt as S2 "
                    "across matched DEV-v3 tasks.",
                    "",
                ]
            )
    if len(summary["experiments"]) == 3:
        lines.extend(
            [
                "## Cross-version perspective",
                "",
                "Historical paired baseline/agent results are not pooled with "
                "DEV-v3's four-arm comparison.",
                "DEV-v3 information-timing arms and shadow measurements distinguish",
                "tool-assisted one-patch behavior from feedback-responsive repair.",
                "",
            ]
        )
        historical = [
            r
            for r in summary["attempts"]
            if r["experiment"] != "dev-v3" and r["arm"] == "agent"
        ]
        if historical and all(
            r["first_patch_shadow_success"] is True for r in historical
        ):
            lines.extend(
                [
                    "In the supplied historical Agent evidence, "
                    "every first mutation prefix already passed the evaluator.",
                    "",
                ]
            )
    lines.extend(["## Validation notes", "", *summary["validation"]["warnings"], ""])
    return "\n".join(lines)


CSV_FIELDS = (
    "experiment",
    "experiment_id",
    "task_id",
    "task_class",
    "task_role",
    "arm",
    "repetition",
    "success",
    "functional_tests_passed",
    "lint_only_failure",
    *METRICS,
    "iterative_occurrence",
    "first_patch_shadow_success",
    "mutation_prefixes",
    "returned_model",
    "routed_provider",
    "git_commit",
    "docker_image_id",
)


def render_attempts_csv(summary: dict) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in summary["attempts"]:
        selected = {key: row.get(key) for key in CSV_FIELDS}
        for key, value in selected.items():
            if isinstance(value, list):
                selected[key] = json.dumps(value, ensure_ascii=False)
            # CSV consumers must not interpret model/provider IDs as formulae.
            elif isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
                selected[key] = "'" + value
        writer.writerow(selected)
    return output.getvalue()


def write_analysis(summary: dict, output_dir: Path) -> None:
    """Exclusive output directory creation; never overwrite existing artifacts."""
    outputs = {
        "summary.json": stable_json(summary),
        "report.md": render_report(summary),
        "attempts.csv": render_attempts_csv(summary),
    }
    output_dir.mkdir()  # parent must exist; existing directory fails closed
    for name, content in outputs.items():
        with (output_dir / name).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
