import shutil
import subprocess
from collections.abc import Iterator, Sequence
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

import coderepair.baseline as baseline
from coderepair.evaluator import EvaluationResult
from coderepair.file_changes import FileChange
from coderepair.generation import GenerationResult, GenerationUsage
from coderepair.repair_context import build_initial_context, render_initial_context
from coderepair.run_config import RunConfig
from coderepair.tasks import load_task
from coderepair.workspace import Workspace, create_workspace, destroy_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_001_DIRECTORY = PROJECT_ROOT / "benchmarks" / "dev" / "dev-001"
DEV_001_MANIFEST = DEV_001_DIRECTORY / "task.yaml"
DEV_001_SNAPSHOT = DEV_001_DIRECTORY / "repo"
SANDBOX_IMAGE = "coderepair-lab-sandbox:dev"
RUN_CONFIG = RunConfig(
    model="fake-model",
    reasoning_effort="medium",
    max_output_tokens=4096,
    request_timeout_seconds=60,
    evaluator_timeout_seconds=30,
    max_file_bytes=100_000,
    max_total_bytes=200_000,
    docker_image=SANDBOX_IMAGE,
)

CORRECT_REPAIR = (
    '"""Small text normalization helpers."""\n\n\n'
    "def normalize_name(value: str) -> str:\n"
    '    """Remove surrounding whitespace from a name."""\n'
    "    return value.strip()\n"
)
INCORRECT_REPAIR = CORRECT_REPAIR.replace("return value.strip()", "return value")
FAKE_USAGE = GenerationUsage(100, 20, 120)


def generation(*changes: FileChange) -> GenerationResult:
    return GenerationResult(changes, FAKE_USAGE, 0.5, "fake", "fake-model")


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[Workspace]:
    result = create_workspace(DEV_001_MANIFEST, tmp_path / "workspace")
    yield result
    destroy_workspace(result)


def run_baseline(
    workspace: Workspace,
    generator: baseline.RepairGenerator,
) -> baseline.SingleShotResult:
    return baseline.run_single_shot_baseline(
        DEV_001_MANIFEST,
        workspace,
        generator=generator,
        config=RUN_CONFIG,
    )


def failed_evaluation() -> EvaluationResult:
    return EvaluationResult(False, True, (), None, None, None)


def test_manifest_mismatch_fails_before_inference_or_mutation(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    mismatched_workspace = replace(
        workspace, task=replace(workspace.task, id="different-task")
    )
    before = {
        path.relative_to(workspace.root): path.read_bytes()
        for path in workspace.root.rglob("*")
        if path.is_file()
    }
    generator_calls = 0

    def generator(prompt: str) -> GenerationResult:
        nonlocal generator_calls
        generator_calls += 1
        return generation()

    def unexpected_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("mismatched manifest must fail before work begins")

    monkeypatch.setattr(baseline, "build_initial_context", unexpected_call)
    monkeypatch.setattr(baseline, "apply_file_changes", unexpected_call)
    monkeypatch.setattr(baseline, "evaluate_workspace", unexpected_call)

    with pytest.raises(ValueError, match="does not match"):
        run_baseline(mismatched_workspace, generator)

    assert generator_calls == 0
    after = {
        path.relative_to(workspace.root): path.read_bytes()
        for path in workspace.root.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_missing_manifest_fails_before_generator(
    workspace: Workspace, tmp_path: Path
) -> None:
    generator_calls = 0

    def generator(prompt: str) -> GenerationResult:
        nonlocal generator_calls
        generator_calls += 1
        return generation()

    with pytest.raises(FileNotFoundError):
        baseline.run_single_shot_baseline(
            tmp_path / "missing.yaml",
            workspace,
            generator=generator,
            config=RUN_CONFIG,
        )

    assert generator_calls == 0


def test_missing_withheld_file_fails_before_model_or_mutation(
    workspace: Workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "withheld-task.yaml"
    manifest.write_text(
        DEV_001_MANIFEST.read_text(encoding="utf-8")
        + "\ncontext_withheld_paths:\n  - missing.py\n",
        encoding="utf-8",
    )
    constrained = replace(workspace, task=load_task(manifest))
    source = workspace.root / "text_utils.py"
    before = source.read_bytes()
    generator_calls = 0

    def generator(_prompt: str) -> GenerationResult:
        nonlocal generator_calls
        generator_calls += 1
        return generation()

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mutation and evaluation must not run")

    monkeypatch.setattr(baseline, "apply_file_changes", unexpected)
    monkeypatch.setattr(baseline, "evaluate_workspace", unexpected)
    with pytest.raises(ValueError, match="missing.py"):
        baseline.run_single_shot_baseline(
            manifest, constrained, generator=generator, config=RUN_CONFIG
        )

    assert generator_calls == 0
    assert source.read_bytes() == before


def test_duration_covers_completed_single_shot_path(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    ticks = iter((10.0, 14.25))

    def clock() -> float:
        events.append("clock")
        return next(ticks)

    def generator(prompt: str) -> GenerationResult:
        events.append("generator")
        return generation(FileChange("text_utils.py", CORRECT_REPAIR))

    def evaluate(*args: object, **kwargs: object) -> EvaluationResult:
        events.append("evaluation")
        return EvaluationResult(True, True, (), None, None, None)

    monkeypatch.setattr(baseline, "perf_counter", clock)
    monkeypatch.setattr(baseline, "evaluate_workspace", evaluate)

    result = run_baseline(workspace, generator)

    assert events == ["clock", "generator", "evaluation", "clock"]
    assert result.duration_seconds == 4.25
    assert result.success


def test_rejected_mutation_still_has_strategy_duration(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter((20.0, 20.75))
    monkeypatch.setattr(baseline, "perf_counter", lambda: next(ticks))

    def unexpected(*args: object, **kwargs: object) -> EvaluationResult:
        raise AssertionError("rejected mutation must not be evaluated")

    monkeypatch.setattr(baseline, "evaluate_workspace", unexpected)
    result = run_baseline(
        workspace,
        lambda prompt: generation(FileChange("tests/test_text_utils.py", "bad")),
    )

    assert result.evaluation is None
    assert not result.success
    assert result.duration_seconds == 0.75


def test_prompt_uses_shared_context_once_and_generator_runs_once(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts: list[str] = []
    evaluations: list[Workspace] = []
    proposal = generation()

    def generator(prompt: str) -> GenerationResult:
        prompts.append(prompt)
        return proposal

    def fake_evaluate(
        task_manifest: Path,
        evaluated_workspace: Workspace,
        *,
        image: str,
        timeout_seconds: float,
    ) -> EvaluationResult:
        assert task_manifest == DEV_001_MANIFEST
        assert image == SANDBOX_IMAGE
        assert timeout_seconds == 30
        evaluations.append(evaluated_workspace)
        return failed_evaluation()

    monkeypatch.setattr(baseline, "evaluate_workspace", fake_evaluate)
    result = run_baseline(workspace, generator)
    shared = render_initial_context(
        build_initial_context(
            workspace, max_file_bytes=100_000, max_total_bytes=200_000
        )
    )

    assert len(prompts) == 1
    assert prompts[0].count(shared) == 1
    assert prompts[0].startswith(shared)
    assert result.initial_context_sha256 == sha256(shared.encode("utf-8")).hexdigest()
    assert "one attempt" in prompts[0]
    assert str(workspace.root) not in prompts[0]
    assert str(workspace.root.parent) not in prompts[0]
    for command in (
        workspace.task.reproduction_test,
        workspace.task.full_test,
        workspace.task.lint,
    ):
        assert repr(command) not in prompts[0]
    assert evaluations == [workspace]
    assert result.mutation_applied
    assert result.generation is proposal
    assert result.mutation_error is None
    assert not result.success


def test_baseline_forwards_shared_config_to_context_and_evaluator(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = replace(
        RUN_CONFIG,
        max_file_bytes=17,
        max_total_bytes=23,
        docker_image="custom-sandbox:dev",
        evaluator_timeout_seconds=7,
    )
    actual_build = baseline.build_initial_context
    context_limits: list[tuple[int, int]] = []
    evaluator_settings: list[tuple[str, float]] = []

    def tracked_build(
        target_workspace: Workspace, *, max_file_bytes: int, max_total_bytes: int
    ) -> baseline.InitialRepairContext:
        context_limits.append((max_file_bytes, max_total_bytes))
        return actual_build(
            target_workspace,
            max_file_bytes=max_file_bytes,
            max_total_bytes=max_total_bytes,
        )

    def tracked_evaluate(
        task_manifest: Path,
        target_workspace: Workspace,
        *,
        image: str,
        timeout_seconds: float,
    ) -> EvaluationResult:
        assert task_manifest == DEV_001_MANIFEST
        assert target_workspace == workspace
        evaluator_settings.append((image, timeout_seconds))
        return failed_evaluation()

    monkeypatch.setattr(baseline, "build_initial_context", tracked_build)
    monkeypatch.setattr(baseline, "evaluate_workspace", tracked_evaluate)
    result = baseline.run_single_shot_baseline(
        DEV_001_MANIFEST,
        workspace,
        generator=lambda prompt: generation(),
        config=config,
    )

    assert context_limits == [(17, 23)]
    assert evaluator_settings == [("custom-sandbox:dev", 7)]
    assert result.evaluation is not None


def test_protected_change_is_rejected_without_evaluation(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = workspace.root / "tests" / "test_text_utils.py"
    before = protected.read_bytes()
    snapshot_before = (DEV_001_SNAPSHOT / "tests" / "test_text_utils.py").read_bytes()
    calls = 0
    proposal = generation(FileChange("tests/test_text_utils.py", "changed\n"))

    def generator(prompt: str) -> GenerationResult:
        nonlocal calls
        calls += 1
        return proposal

    def unexpected_evaluation(*args: object, **kwargs: object) -> EvaluationResult:
        raise AssertionError("rejected mutation must not be evaluated")

    monkeypatch.setattr(baseline, "evaluate_workspace", unexpected_evaluation)
    result = run_baseline(workspace, generator)

    assert calls == 1
    assert not result.mutation_applied
    assert result.generation is proposal
    assert result.mutation_error is not None
    assert result.evaluation is None
    assert protected.read_bytes() == before
    snapshot_test = DEV_001_SNAPSHOT / "tests" / "test_text_utils.py"
    assert snapshot_test.read_bytes() == snapshot_before
    assert str(workspace.root) not in result.mutation_error


def test_mixed_allowed_and_protected_changes_apply_nothing(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = workspace.root / "text_utils.py"
    protected = workspace.root / "tests" / "test_text_utils.py"
    before_source = source.read_bytes()
    before_protected = protected.read_bytes()

    def unexpected_evaluation(*args: object, **kwargs: object) -> EvaluationResult:
        raise AssertionError("rejected batch must not be evaluated")

    monkeypatch.setattr(baseline, "evaluate_workspace", unexpected_evaluation)
    result = run_baseline(
        workspace,
        lambda prompt: generation(
            FileChange("text_utils.py", CORRECT_REPAIR),
            FileChange("tests/test_text_utils.py", "changed\n"),
        ),
    )

    assert not result.mutation_applied
    assert result.evaluation is None
    assert source.read_bytes() == before_source
    assert protected.read_bytes() == before_protected
    assert (DEV_001_SNAPSHOT / "text_utils.py").read_bytes() == before_source


def test_traversal_change_is_rejected_without_evaluation(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = workspace.root.parent / "outside.py"

    def unexpected_evaluation(*args: object, **kwargs: object) -> EvaluationResult:
        raise AssertionError("rejected traversal must not be evaluated")

    monkeypatch.setattr(baseline, "evaluate_workspace", unexpected_evaluation)
    result = run_baseline(
        workspace, lambda prompt: generation(FileChange("../outside.py", "changed\n"))
    )

    assert not result.mutation_applied
    assert result.evaluation is None
    assert not outside.exists()


@pytest.mark.parametrize(
    "proposal",
    [
        None,
        "bad",
        [{"path": "text_utils.py"}],
        [FileChange("text_utils.py", CORRECT_REPAIR)],
        (FileChange("text_utils.py", CORRECT_REPAIR),),
    ],
)
def test_invalid_generator_output_is_rejected_before_mutation(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch, proposal: object
) -> None:
    before = (workspace.root / "text_utils.py").read_bytes()

    def unexpected_mutation(*args: object, **kwargs: object) -> None:
        raise AssertionError("invalid output must not reach mutation")

    def unexpected_evaluation(*args: object, **kwargs: object) -> EvaluationResult:
        raise AssertionError("invalid output must not reach evaluation")

    monkeypatch.setattr(baseline, "apply_file_changes", unexpected_mutation)
    monkeypatch.setattr(baseline, "evaluate_workspace", unexpected_evaluation)
    with pytest.raises(ValueError, match="GenerationResult"):
        run_baseline(workspace, lambda prompt: proposal)  # type: ignore[return-value]

    assert (workspace.root / "text_utils.py").read_bytes() == before


def test_generator_exception_propagates(workspace: Workspace) -> None:
    def broken_generator(prompt: str) -> GenerationResult:
        raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        run_baseline(workspace, broken_generator)


def test_mutation_error_does_not_expose_host_path(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    def rejected_mutation(*args: object, **kwargs: object) -> None:
        target = workspace.root / "text_utils.py"
        raise ValueError(f"linked target is not allowed: {target}")

    def unexpected_evaluation(*args: object, **kwargs: object) -> EvaluationResult:
        raise AssertionError("rejected mutation must not be evaluated")

    monkeypatch.setattr(baseline, "apply_file_changes", rejected_mutation)
    monkeypatch.setattr(baseline, "evaluate_workspace", unexpected_evaluation)
    result = run_baseline(
        workspace,
        lambda prompt: generation(FileChange("text_utils.py", CORRECT_REPAIR)),
    )

    assert not result.mutation_applied
    assert result.evaluation is None
    assert result.mutation_error is not None
    assert "text_utils.py" in result.mutation_error
    assert str(workspace.root) not in result.mutation_error
    assert str(workspace.root.parent) not in result.mutation_error


@pytest.fixture(scope="module")
def docker_image() -> str:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")
    try:
        daemon = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"Docker daemon is unavailable: {error}")
    if daemon.returncode != 0:
        pytest.skip("Docker daemon is unavailable")

    image = subprocess.run(
        ["docker", "image", "inspect", SANDBOX_IMAGE],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if image.returncode != 0:
        pytest.skip(f"sandbox image is unavailable: {SANDBOX_IMAGE}")
    return SANDBOX_IMAGE


def test_correct_single_shot_repair_succeeds(
    workspace: Workspace, docker_image: str
) -> None:
    original = (DEV_001_SNAPSHOT / "text_utils.py").read_bytes()
    calls = 0
    proposal = generation(FileChange("text_utils.py", CORRECT_REPAIR))

    def generator(prompt: str) -> GenerationResult:
        nonlocal calls
        calls += 1
        return proposal

    result = run_baseline(workspace, generator)

    assert calls == 1
    assert result.generation is proposal
    assert result.changes == proposal.changes
    assert result.mutation_applied
    assert result.mutation_error is None
    assert result.success
    assert result.evaluation is not None
    assert result.evaluation.reproduction.exit_code == 0
    assert result.evaluation.full_test.exit_code == 0
    assert result.evaluation.lint.exit_code == 0
    assert (DEV_001_SNAPSHOT / "text_utils.py").read_bytes() == original


def test_incorrect_single_shot_repair_is_not_retried(
    workspace: Workspace, docker_image: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = (DEV_001_SNAPSHOT / "text_utils.py").read_bytes()
    real_evaluate = baseline.evaluate_workspace
    real_mutation = baseline.apply_file_changes
    calls = 0
    evaluations = 0
    mutations = 0
    proposal = generation(FileChange("text_utils.py", INCORRECT_REPAIR))

    def generator(prompt: str) -> GenerationResult:
        nonlocal calls
        calls += 1
        return proposal

    def counted_evaluate(*args: object, **kwargs: object) -> EvaluationResult:
        nonlocal evaluations
        evaluations += 1
        return real_evaluate(*args, **kwargs)  # type: ignore[arg-type]

    def counted_mutation(
        target_workspace: Workspace, changes: Sequence[FileChange]
    ) -> None:
        nonlocal mutations
        mutations += 1
        real_mutation(target_workspace, changes)

    monkeypatch.setattr(baseline, "evaluate_workspace", counted_evaluate)
    monkeypatch.setattr(baseline, "apply_file_changes", counted_mutation)
    result = run_baseline(workspace, generator)

    assert calls == 1
    assert result.generation is proposal
    assert evaluations == 1
    assert mutations == 1
    assert result.mutation_applied
    assert result.evaluation is not None
    assert not result.evaluation.success
    assert not result.success
    assert (DEV_001_SNAPSHOT / "text_utils.py").read_bytes() == original


def test_empty_proposal_evaluates_original_once(
    workspace: Workspace, docker_image: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = (DEV_001_SNAPSHOT / "text_utils.py").read_bytes()
    real_evaluate = baseline.evaluate_workspace
    calls = 0
    evaluations = 0
    proposal = generation()

    def generator(prompt: str) -> GenerationResult:
        nonlocal calls
        calls += 1
        return proposal

    def counted_evaluate(*args: object, **kwargs: object) -> EvaluationResult:
        nonlocal evaluations
        evaluations += 1
        return real_evaluate(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(baseline, "evaluate_workspace", counted_evaluate)
    result = run_baseline(workspace, generator)

    assert calls == 1
    assert result.generation is proposal
    assert evaluations == 1
    assert result.changes == ()
    assert result.mutation_applied
    assert result.mutation_error is None
    assert result.evaluation is not None
    assert not result.evaluation.success
    assert not result.success
    assert (workspace.root / "text_utils.py").read_bytes() == original
    assert (DEV_001_SNAPSHOT / "text_utils.py").read_bytes() == original
