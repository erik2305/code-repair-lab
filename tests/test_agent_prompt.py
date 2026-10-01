import pytest

from coderepair.agent_prompt import render_agent_step_prompt, render_agent_transcript
from coderepair.agent_protocol import (
    AgentObservation,
    AgentTranscriptEntry,
    ApplyFileChangesAction,
    ReadFileAction,
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
)
from coderepair.file_changes import FileChange
from coderepair.repair_context import (
    ContextFile,
    InitialRepairContext,
    render_initial_context,
)


def context() -> InitialRepairContext:
    return InitialRepairContext(
        task_id="dev-001",
        bug_description="Surrounding whitespace remains.",
        writable_paths=("*.py",),
        protected_paths=("tests/**",),
        repository_paths=("tests/test_name.py", "text_utils.py"),
        files=(ContextFile("text_utils.py", "def normalize_name(value):\n    pass\n"),),
        omitted_paths=("binary.dat",),
    )


def render(
    transcript: tuple[AgentTranscriptEntry, ...] = (),
    *,
    model_calls_remaining: int = 2,
    tool_calls_remaining: int = 5,
) -> str:
    return render_agent_step_prompt(
        context(), transcript,
        model_calls_remaining=model_calls_remaining,
        tool_calls_remaining=tool_calls_remaining,
    )


def entry(action: object, content: str, *, error: bool = False) -> AgentTranscriptEntry:
    names = {
        ReadFileAction: "read_file",
        ApplyFileChangesAction: "apply_file_changes",
        RunReproductionAction: "run_reproduction",
        RunFullTestsAction: "run_full_tests",
        RunLintAction: "run_lint",
    }
    return AgentTranscriptEntry(
        action=action,
        observation=AgentObservation(names[type(action)], content, error),
    )


def test_shared_context_is_embedded_verbatim_once() -> None:
    shared = render_initial_context(context())
    prompt = render()

    assert prompt.count(shared) == 1
    assert "=== INITIAL REPAIR CONTEXT ===\n" + shared in prompt
    assert shared + "=== END INITIAL REPAIR CONTEXT ===" in prompt
    assert prompt.index("=== INITIAL REPAIR CONTEXT ===") < prompt.index(
        "=== REMAINING BUDGET ==="
    )
    assert prompt.index("=== REMAINING BUDGET ===") < prompt.index(
        "=== TOOL HISTORY ==="
    )


def test_empty_history_and_zero_budgets_are_explicit_and_deterministic() -> None:
    prompt = render(model_calls_remaining=0, tool_calls_remaining=0)

    assert prompt == render(model_calls_remaining=0, tool_calls_remaining=0)
    assert "=== TOOL HISTORY ===\n(no tool actions yet)\n" in prompt
    assert "Model calls remaining: 0\nTool calls remaining: 0\n" in prompt
    assert render_agent_transcript(()) == "(no tool actions yet)"


def test_static_prefix_is_stable_across_budget_and_history() -> None:
    first = render(model_calls_remaining=3, tool_calls_remaining=4)
    later = render(
        (entry(ReadFileAction("text_utils.py"), "observation"),),
        model_calls_remaining=1,
        tool_calls_remaining=2,
    )
    boundary = "=== REMAINING BUDGET ==="
    assert first.split(boundary, 1)[0] == later.split(boundary, 1)[0]
    assert first.count(render_initial_context(context())) == 1
    assert later.count(render_initial_context(context())) == 1


def test_ordered_history_renders_all_tool_actions_without_file_contents() -> None:
    sentinel = "UNIQUE_GENERATED_SOURCE_SENTINEL"
    transcript = (
        entry(ReadFileAction("tests/test_name.py"), "file read"),
        entry(
            ApplyFileChangesAction(
                (FileChange("text_utils.py", sentinel), FileChange("other.py", "x"))
            ),
            "two files changed",
        ),
        entry(RunReproductionAction(), "reproduction failed"),
        entry(RunFullTestsAction(), "full suite failed"),
        entry(RunLintAction(), "lint passed"),
    )

    prompt = render(transcript)

    positions = [prompt.index(f"Step {index}\nAction: {name}") for index, name in (
        (1, "read_file"), (2, "apply_file_changes"), (3, "run_reproduction"),
        (4, "run_full_tests"), (5, "run_lint"),
    )]
    assert positions == sorted(positions)
    assert render_agent_transcript(transcript) in prompt
    assert "Path: tests/test_name.py" in prompt
    assert "Files:\n- text_utils.py\n- other.py" in prompt
    assert sentinel not in prompt
    for name in (
        "read_file", "apply_file_changes", "run_reproduction",
        "run_full_tests", "run_lint",
    ):
        assert f"Tool: {name}\nStatus: ok\nContent:" in prompt


def test_observation_content_is_preserved_and_error_is_marked() -> None:
    content = "first line\n  second line\nthird line"
    prompt = render((entry(RunReproductionAction(), content, error=True),))

    assert "Tool: run_reproduction\nStatus: error\nContent:\n" + content in prompt
    assert prompt.count(content) == 1


def test_prompt_states_action_and_cumulative_success_semantics() -> None:
    prompt = render()

    for name in (
        "read_file", "apply_file_changes", "run_reproduction",
        "run_full_tests", "run_lint", "finish",
    ):
        assert f"- {name}:" in prompt
    assert "Choose exactly one next action" in prompt
    assert "Successful file changes persist into subsequent steps" in prompt
    assert "There is no implicit rollback or checkpoint" in prompt
    assert "Failed or rejected tool calls do not change the repository" in prompt
    assert "finish does not mean success" in prompt
    assert "final independent evaluator determines benchmark correctness" in prompt


@pytest.mark.parametrize("bad_context", [None, "context", object()])
def test_rejects_invalid_context(bad_context: object) -> None:
    with pytest.raises(ValueError, match="context"):
        render_agent_step_prompt(
            bad_context, (), model_calls_remaining=1, tool_calls_remaining=1
        )


@pytest.mark.parametrize("bad_transcript", [[], (object(),), None])
def test_rejects_invalid_transcript(bad_transcript: object) -> None:
    with pytest.raises(ValueError, match="transcript"):
        render_agent_step_prompt(
            context(), bad_transcript,
            model_calls_remaining=1, tool_calls_remaining=1,
        )
    with pytest.raises(ValueError, match="transcript"):
        render_agent_transcript(bad_transcript)


@pytest.mark.parametrize("field", ["model_calls_remaining", "tool_calls_remaining"])
@pytest.mark.parametrize("bad_value", [-1, True, False, 1.5, "1", None])
def test_rejects_invalid_remaining_budget(field: str, bad_value: object) -> None:
    kwargs = {"model_calls_remaining": 1, "tool_calls_remaining": 1}
    kwargs[field] = bad_value
    with pytest.raises(ValueError, match=field):
        render_agent_step_prompt(context(), (), **kwargs)
