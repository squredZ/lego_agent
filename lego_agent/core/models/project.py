from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lego_agent.core.models.base import new_id, utc_now
from lego_agent.core.models.enums import ProjectStatus
from lego_agent.core.models.errors import ProjectError
from lego_agent.core.models.events import ProjectEvent
from lego_agent.core.models.staff import Staff
from lego_agent.core.models.staffing import ProjectResult, StaffProfileResolution, StaffingPlan
from lego_agent.core.models.task import Task


class Project(BaseModel):
    """Top-level runtime aggregate.

    A Project owns staff, tasks, status, and final output. It replaces the old
    Organization concept as the only public runtime aggregate.
    """

    model_config = ConfigDict(use_enum_values=False, arbitrary_types_allowed=True)

    id: str = Field(default_factory=new_id, description="Unique project id for runtime tracking.")
    goal: str = Field(description="Original user goal that the project should accomplish.")
    name: str | None = Field(default=None, description="Optional short display name for the project.")
    description: str | None = Field(default=None, description="Optional longer project description.")
    status: ProjectStatus = Field(default=ProjectStatus.CREATED, description="Current project lifecycle state.")
    manager_id: str = Field(description="Staff id of the mandatory primary project manager.")
    staff: dict[str, Staff] = Field(default_factory=dict, description="Project staff keyed by staff id.")
    tasks: dict[str, Task] = Field(default_factory=dict, description="Project tasks keyed by task id.")
    staffing_plan: StaffingPlan | None = Field(default=None, description="Latest staffing plan produced by the project manager.")
    result: ProjectResult | None = Field(default=None, description="Latest project-level result produced by the project manager.")
    error: ProjectError | None = Field(default=None, description="Terminal project error when status is failed.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp when the project was created.")
    updated_at: datetime | None = Field(default=None, description="Timestamp when project state was last updated.")
    completed_at: datetime | None = Field(default=None, description="Timestamp for terminal project completion or failure.")
    events: list[ProjectEvent] = Field(default_factory=list, description="In-memory project event history for observability.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extension data that does not belong in first-class fields.")

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
    """Return object for one project run through CLI, API, or tests."""

    model_config = ConfigDict(use_enum_values=False)

    run_id: str = Field(default_factory=new_id, description="Unique id for this runtime invocation.")
    project_id: str = Field(description="Project id created or executed by this run.")
    project_goal: str = Field(description="User goal used for the run.")
    status: ProjectStatus = Field(description="Project status when the run returned.")
    manager_id: str = Field(description="Primary project manager staff id.")
    manager_name: str = Field(description="Human-readable project manager name.")
    result: ProjectResult | None = Field(default=None, description="Project-level result when available.")
    staffing_profile_resolution: StaffProfileResolution | None = Field(default=None, description="How planned roles map to configured or dynamic staff.")
    error: ProjectError | None = Field(default=None, description="Run or project error when execution failed.")
    events: list[ProjectEvent] = Field(default_factory=list, description="Project events emitted during the run.")
    started_at: datetime = Field(default_factory=utc_now, description="Run start timestamp.")
    completed_at: datetime | None = Field(default=None, description="Run completion timestamp.")
    duration_ms: int | None = Field(default=None, description="Run duration in milliseconds.")
