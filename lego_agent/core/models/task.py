from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lego_agent.core.models.base import new_id, utc_now
from lego_agent.core.models.enums import TaskStatus
from lego_agent.core.models.errors import TaskError
from lego_agent.core.models.events import TaskEvent


class Task(BaseModel):
    """Unit of work assigned to a staff member inside a project."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(default_factory=new_id, description="Unique task id.")
    project_id: str = Field(description="Project that owns this task.")
    title: str = Field(description="Short human-readable task title.")
    goal: str = Field(description="Concrete objective the assignee should accomplish.")
    assigned_to: str | None = Field(default=None, description="Staff id currently assigned to the task.")
    created_by: str | None = Field(default=None, description="Staff id or system actor that created the task.")
    parent_task_id: str | None = Field(default=None, description="Parent task id for decomposed child tasks.")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current task lifecycle state.")
    result: str | None = Field(default=None, description="Final text output stored when the task completes.")
    error: TaskError | None = Field(default=None, description="Task error details when execution fails.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp when the task was created.")
    updated_at: datetime | None = Field(default=None, description="Timestamp when task state was last updated.")
    started_at: datetime | None = Field(default=None, description="Timestamp when work started.")
    completed_at: datetime | None = Field(default=None, description="Timestamp when the task reached done or failed.")
    events: list[TaskEvent] = Field(default_factory=list, description="In-memory task event history.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extension data that does not need a first-class field.")
