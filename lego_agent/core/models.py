from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


def new_id() -> str:
    """Create ids in one place so model defaults stay consistent."""
    return str(uuid4())


def utc_now() -> datetime:
    """Use timezone-aware UTC timestamps throughout runtime models."""
    return datetime.now(UTC)


class ProjectStatus(StrEnum):
    CREATED = "created"
    PLANNING = "planning"
    STAFFING = "staffing"
    RUNNING = "running"
    REVIEWING = "reviewing"
    DONE = "done"
    FAILED = "failed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class StaffStatus(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    OFFLINE = "offline"


class EventLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ProjectError(BaseModel):
    type: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class TaskError(BaseModel):
    type: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class Responsibility(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str


class Capability(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str


class Staff(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, use_enum_values=False)

    id: str
    project_id: str
    name: str
    role: str
    title: str
    description: str | None = None
    responsibilities: list[Responsibility] = Field(default_factory=list)
    capabilities: list[Capability] = Field(default_factory=list)
    assistant: Assistant | None = None
    manager_id: str | None = None
    report_ids: list[str] = Field(default_factory=list)
    status: StaffStatus = StaffStatus.IDLE
    current_task_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def assign(self, task: Task) -> None:
        logger.debug(
            "staff assigned task",
            extra={"project_id": self.project_id, "staff_id": self.id, "task_id": task.id},
        )
        self.current_task_id = task.id
        self.status = StaffStatus.WORKING
        task.status = TaskStatus.IN_PROGRESS
        task.assigned_to = self.id
        task.started_at = utc_now()

    def complete(self, task: Task, result: str) -> str:
        logger.debug(
            "staff completed task",
            extra={
                "project_id": self.project_id,
                "staff_id": self.id,
                "task_id": task.id,
                "result_length": len(result),
            },
        )
        task.status = TaskStatus.DONE
        task.result = result
        self.status = StaffStatus.IDLE
        self.current_task_id = None
        task.completed_at = utc_now()
        return result


class Task(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(default_factory=new_id)
    project_id: str
    title: str
    goal: str
    assigned_to: str | None = None
    created_by: str | None = None
    parent_task_id: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    error: TaskError | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    events: list[TaskEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StaffRolePlan(BaseModel):
    role: str
    title: str
    responsibilities: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    task_focus: str
    priority: int = 1


class StaffingPlan(BaseModel):
    required_roles: list[StaffRolePlan] = Field(default_factory=list)
    rationale: str


class ProjectResult(BaseModel):
    summary: str
    project_understanding: str
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    staffing_plan: StaffingPlan
    task_breakdown: list[str] = Field(default_factory=list)
    execution_plan: list[str] = Field(default_factory=list)
    final_output: str


class StaffProfileMatch(BaseModel):
    """Result of matching one planned role to a configured staff profile."""

    planned_role: str
    planned_title: str
    matched: bool
    profile_name: str | None = None
    profile_role: str | None = None
    profile_title: str | None = None
    reason: str


class StaffProfileResolution(BaseModel):
    """All configured profile matches for one project staffing plan."""

    matches: list[StaffProfileMatch] = Field(default_factory=list)

    @property
    def unresolved(self) -> list[StaffProfileMatch]:
        """Return planned roles that cannot be created from current config."""
        return [match for match in self.matches if not match.matched]


class OutputContract(BaseModel):
    """Describes the structured output expected from an assistant."""

    name: str
    json_schema: dict[str, Any]
    instructions: str


class Project(BaseModel):
    """Top-level runtime aggregate.

    A Project owns staff, tasks, status, and final output. It replaces the old
    Organization concept as the only public runtime aggregate.
    """

    model_config = ConfigDict(use_enum_values=False, arbitrary_types_allowed=True)

    id: str = Field(default_factory=new_id)
    goal: str
    name: str | None = None
    description: str | None = None
    status: ProjectStatus = ProjectStatus.CREATED
    manager_id: str
    staff: dict[str, Staff] = Field(default_factory=dict)
    tasks: dict[str, Task] = Field(default_factory=dict)
    staffing_plan: StaffingPlan | None = None
    result: ProjectResult | None = None
    error: ProjectError | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    events: list[ProjectEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_manager(self) -> Project:
        """Ensure every project has one valid primary project manager."""
        manager = self.staff.get(self.manager_id)
        if manager is None:
            raise ValueError(f"project manager '{self.manager_id}' is not in project staff")
        if manager.role != "project_manager":
            raise ValueError("primary project manager staff must use role 'project_manager'")
        return self

    @property
    def manager(self) -> Staff:
        return self.staff[self.manager_id]


class ProjectRunResult(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    run_id: str = Field(default_factory=new_id)
    project_id: str
    project_goal: str
    status: ProjectStatus
    manager_id: str
    manager_name: str
    result: ProjectResult | None = None
    staffing_profile_resolution: StaffProfileResolution | None = None
    error: ProjectError | None = None
    events: list[ProjectEvent] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    duration_ms: int | None = None


class WorkContext(BaseModel):
    project_id: str
    task_id: str
    staff_id: str
    project_goal: str
    task_goal: str
    role_context: str | None = None
    task_context: str | None = None
    memory_context: str | None = None
    tool_context: str | None = None
    skill_context: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


class ProjectEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    type: str
    message: str
    level: EventLevel = EventLevel.INFO
    actor_id: str | None = None
    task_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class TaskEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    project_id: str
    task_id: str
    type: str
    message: str
    level: EventLevel = EventLevel.INFO
    actor_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class Message(BaseModel):
    role: str
    content: str


class AssistantRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    project: Project
    staff: Staff
    task: Task
    context: WorkContext
    messages: list[Message] = Field(default_factory=list)
    output_contract: OutputContract | None = None
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssistantResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    content: str
    structured: dict[str, Any] = Field(default_factory=dict)
    raw: Any | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class Assistant(Protocol):
    """Common interface implemented by model provider adapters."""

    def respond(self, request: AssistantRequest) -> AssistantResponse:
        """Return an assistant response for a staff workflow request."""


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    content: str | None = None
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class SkillSpec(BaseModel):
    name: str
    description: str
    instructions: str
    required_capabilities: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)


class MemoryItem(BaseModel):
    id: str = Field(default_factory=new_id)
    scope: str
    content: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class WorkResult(BaseModel):
    staff_id: str
    task_id: str
    status: TaskStatus
    output: str | None = None
    project_result: ProjectResult | None = None
    error: TaskError | None = None
