from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import SkipJsonSchema

from lego_agent.core.models.assistant import Assistant
from lego_agent.core.models.base import utc_now
from lego_agent.core.models.capabilities import Capability, Responsibility
from lego_agent.core.models.enums import StaffStatus, TaskStatus
from lego_agent.core.models.task import Task

logger = logging.getLogger(__name__)


class Staff(BaseModel):
    """Unified project member model used for managers and recruited workers."""

    model_config = ConfigDict(arbitrary_types_allowed=True, use_enum_values=False)

    id: str = Field(description="Stable staff id used in tasks, messages, and events.")
    project_id: str = Field(description="Project that owns this staff member.")
    name: str = Field(description="Human-readable staff name.")
    role: str = Field(description="Stable role identifier, such as project_manager or frontend_developer.")
    title: str = Field(description="Human-readable role title shown to users.")
    description: str | None = Field(default=None, description="Optional explanation of this staff member's purpose.")
    responsibilities: list[Responsibility] = Field(default_factory=list, description="Accountabilities this staff member should fulfill.")
    capabilities: list[Capability] = Field(default_factory=list, description="Abilities this staff member can apply while working.")
    assistant: SkipJsonSchema[Assistant | None] = Field(default=None, description="AI assistant adapter used by this staff member.")
    manager_id: str | None = Field(default=None, description="Staff id of this member's manager, if any.")
    report_ids: list[str] = Field(default_factory=list, description="Staff ids that report to this member.")
    status: StaffStatus = Field(default=StaffStatus.IDLE, description="Current staff working state.")
    current_task_id: str | None = Field(default=None, description="Task currently assigned as active work.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extension data for custom staff behavior.")

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
