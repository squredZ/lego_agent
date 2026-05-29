from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lego_agent.core.models.assistant import Message, OutputContract
from lego_agent.core.models.enums import TaskStatus
from lego_agent.core.models.errors import TaskError
from lego_agent.core.models.project import Project
from lego_agent.core.models.staff import Staff
from lego_agent.core.models.staffing import ProjectResult, TaskExecutionResult
from lego_agent.core.models.task import Task


class WorkContext(BaseModel):
    """Context package built for one staff member executing one task."""

    project_id: str = Field(description="Project id for this work context.")
    task_id: str = Field(description="Task id being executed.")
    staff_id: str = Field(description="Staff id executing the task.")
    project_goal: str = Field(description="Original project goal.")
    task_goal: str = Field(description="Current task goal.")
    role_context: str | None = Field(default=None, description="Role, responsibility, and capability context.")
    task_context: str | None = Field(default=None, description="Additional task-specific context.")
    memory_context: str | None = Field(default=None, description="Relevant memory retrieved before execution.")
    tool_context: str | None = Field(default=None, description="Summary of available tools or tool policy.")
    skill_context: str | None = Field(default=None, description="Selected skill instructions for this task.")
    variables: dict[str, Any] = Field(default_factory=dict, description="Extension variables used by custom workflows.")


class AssistantRequest(BaseModel):
    """Provider-agnostic request sent from a staff workflow to an assistant."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    project: Project = Field(description="Project aggregate available to the assistant adapter.")
    staff: Staff = Field(description="Staff member making the request.")
    task: Task = Field(description="Task being executed.")
    context: WorkContext = Field(description="Prepared workflow context for this task.")
    messages: list[Message] = Field(default_factory=list, description="Conversation messages sent to the model.")
    output_contract: OutputContract | None = Field(default=None, description="Expected structured output contract.")
    output_schema: dict[str, Any] | None = Field(default=None, description="JSON schema for the expected output.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Workflow-specific request metadata.")


class WorkResult(BaseModel):
    """Normalized result returned by a staff workflow after task execution."""

    staff_id: str = Field(description="Staff id that executed the task.")
    task_id: str = Field(description="Task id that was executed.")
    status: TaskStatus = Field(description="Final task status reported by the workflow.")
    output: str | None = Field(default=None, description="Final text output stored on the task.")
    project_result: ProjectResult | None = Field(default=None, description="Structured project manager result, when applicable.")
    task_result: TaskExecutionResult | None = Field(default=None, description="Structured worker task result, when applicable.")
    error: TaskError | None = Field(default=None, description="Task error when workflow execution failed.")
