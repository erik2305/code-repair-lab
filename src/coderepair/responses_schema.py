"""Strict structured-output schemas for the Responses-compatible transport."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from coderepair.agent_protocol import (
    AgentAction,
    ApplyFileChangesAction,
    FinishAction,
    ReadFileAction,
    RunFullTestsAction,
    RunLintAction,
    RunReproductionAction,
)
from coderepair.file_changes import FileChange


class _RepairFileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    content: str


class _RepairProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: list[_RepairFileChange]


class _ReadFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["read_file"]
    path: str


class _ApplyFileChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["apply_file_changes"]
    changes: list[_RepairFileChange]


class _RunReproduction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["run_reproduction"]


class _RunFullTests(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["run_full_tests"]


class _RunLint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["run_lint"]


class _Finish(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["finish"]


class _AgentStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: (
        _ReadFile
        | _ApplyFileChanges
        | _RunReproduction
        | _RunFullTests
        | _RunLint
        | _Finish
    )


def _map_agent_action(proposal: _AgentStep) -> AgentAction:
    """Map one parsed decision to domain intent; execution remains elsewhere."""
    action = proposal.action
    if isinstance(action, _ReadFile):
        return ReadFileAction(path=action.path)
    if isinstance(action, _ApplyFileChanges):
        return ApplyFileChangesAction(
            changes=tuple(
                FileChange(path=change.path, content=change.content)
                for change in action.changes
            )
        )
    if isinstance(action, _RunReproduction):
        return RunReproductionAction()
    if isinstance(action, _RunFullTests):
        return RunFullTestsAction()
    if isinstance(action, _RunLint):
        return RunLintAction()
    if isinstance(action, _Finish):
        return FinishAction()
    raise RuntimeError("unsupported parsed agent action")
