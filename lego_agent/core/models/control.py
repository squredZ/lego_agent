from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from lego_agent.core.models.enums import ProjectStatus, StaffStatus, TaskStatus
from lego_agent.core.models.messages import StaffMessageType


class ManagerAction(StrEnum):
    """Allowed actions a project manager can ask the orchestrator to apply."""

    WAIT = "wait"
    ASSIGN_TASK = "assign_task"
    REVIEW = "review"
    FINISH = "finish"
    FAIL = "fail"
    ASK_USER = "ask_user"


class TaskSnapshot(BaseModel):
    """Read-only task state shown to the manager control loop."""

    task_id: str = Field(description="Task id being summarized.")
    title: str = Field(description="Human-readable task title.")
    assigned_to: str | None = Field(default=None, description="Staff id assigned to the task.")
    status: TaskStatus = Field(description="Current task status.")
    has_result: bool = Field(description="Whether the task has a stored result.")
    has_error: bool = Field(description="Whether the task has a stored error.")


class StaffSnapshot(BaseModel):
    """Read-only staff state shown to the manager control loop."""

    staff_id: str = Field(description="Staff id being summarized.")
    role: str = Field(description="Staff role inside the project.")
    title: str = Field(description="Human-readable staff title.")
    status: StaffStatus = Field(description="Current staff working state.")
    current_task_id: str | None = Field(default=None, description="Task currently owned by this staff member.")


class StaffMessageSnapshot(BaseModel):
    """Read-only staff message summary shown to the manager control loop."""

    message_id: str = Field(description="Message id being summarized.")
    sender_id: str = Field(description="Staff id that sent the message.")
    recipient_id: str = Field(description="Staff id that received the message.")
    type: StaffMessageType = Field(description="Stable message category.")
    task_id: str | None = Field(default=None, description="Related task id, if any.")
    content_summary: str = Field(description="Short message content summary for manager decisions.")


class ProjectSnapshot(BaseModel):
    """Project state collected before a manager decision.

    The snapshot keeps manager decisions read-only. The manager can inspect this
    object and return a decision, but only the orchestrator applies changes.
    """

    project_id: str = Field(description="Project id being controlled.")
    project_status: ProjectStatus = Field(description="Current project status.")
    manager_id: str = Field(description="Primary project manager staff id.")
    tasks: list[TaskSnapshot] = Field(default_factory=list, description="Tasks relevant to the current control round.")
    staff: list[StaffSnapshot] = Field(default_factory=list, description="Current project staff state.")
    unread_manager_message_count: int = Field(default=0, description="Unread messages waiting for the manager.")
    unread_manager_messages: list[StaffMessageSnapshot] = Field(
        default_factory=list,
        description="Unread manager message summaries relevant to the current control round.",
    )
    event_count: int = Field(default=0, description="Number of project events recorded so far.")


class ManagerDecision(BaseModel):
    """Structured decision returned by the manager control loop."""

    action: ManagerAction = Field(description="Allowed action the orchestrator should apply.")
    rationale: str = Field(description="Short reason for the decision.")
    project_status: ProjectStatus | None = Field(
        default=None,
        description="Optional project status the action expects after application.",
    )
    task_ids: list[str] = Field(default_factory=list, description="Tasks relevant to this decision.")
