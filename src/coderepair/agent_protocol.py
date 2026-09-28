"""Provider-neutral intent and observation types for a future repair agent."""

from dataclasses import dataclass
from typing import Literal, TypeAlias

from coderepair.file_changes import FileChange

AgentToolName = Literal[
    "read_file",
    "apply_file_changes",
    "run_reproduction",
    "run_full_tests",
    "run_lint",
]

_TOOL_NAMES = frozenset(
    (
        "read_file",
        "apply_file_changes",
        "run_reproduction",
        "run_full_tests",
        "run_lint",
    )
)


@dataclass(frozen=True, slots=True)
class ReadFileAction:
    """Request a file read; the tool boundary enforces path safety."""

    path: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise ValueError("path must be a non-empty string")


@dataclass(frozen=True, slots=True)
class ApplyFileChangesAction:
    """Propose explicit changes; the mutation boundary validates them."""

    changes: tuple[FileChange, ...]

    def __post_init__(self) -> None:
        if type(self.changes) is not tuple or any(
            not isinstance(change, FileChange) for change in self.changes
        ):
            raise ValueError("changes must be a tuple of FileChange objects")


@dataclass(frozen=True, slots=True)
class RunReproductionAction:
    """Request the task's trusted reproduction check."""


@dataclass(frozen=True, slots=True)
class RunFullTestsAction:
    """Request the task's trusted full test suite."""


@dataclass(frozen=True, slots=True)
class RunLintAction:
    """Request the task's trusted lint command, if configured."""


@dataclass(frozen=True, slots=True)
class FinishAction:
    """Request termination without asserting repair success."""


AgentToolAction: TypeAlias = (
    ReadFileAction
    | ApplyFileChangesAction
    | RunReproductionAction
    | RunFullTestsAction
    | RunLintAction
)
AgentAction: TypeAlias = AgentToolAction | FinishAction


def tool_name_for_action(action: AgentToolAction) -> AgentToolName:
    """Map only an executable action to an existing MCP tool name."""
    if isinstance(action, ReadFileAction):
        return "read_file"
    if isinstance(action, ApplyFileChangesAction):
        return "apply_file_changes"
    if isinstance(action, RunReproductionAction):
        return "run_reproduction"
    if isinstance(action, RunFullTestsAction):
        return "run_full_tests"
    if isinstance(action, RunLintAction):
        return "run_lint"
    raise ValueError("action does not name an executable tool")


@dataclass(frozen=True, slots=True)
class AgentObservation:
    """Model-visible feedback supplied by future tool orchestration."""

    tool: AgentToolName
    content: str
    is_error: bool

    def __post_init__(self) -> None:
        if not isinstance(self.tool, str) or self.tool not in _TOOL_NAMES:
            raise ValueError("tool must be a known agent tool name")
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")
        if type(self.is_error) is not bool:
            raise ValueError("is_error must be a bool")


@dataclass(frozen=True, slots=True)
class AgentTranscriptEntry:
    """One executable intent paired with its matching observation."""

    action: AgentToolAction
    observation: AgentObservation

    def __post_init__(self) -> None:
        if not isinstance(self.observation, AgentObservation):
            raise ValueError("observation must be an AgentObservation")
        if tool_name_for_action(self.action) != self.observation.tool:
            raise ValueError("action and observation tool do not match")
