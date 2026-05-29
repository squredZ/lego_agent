from __future__ import annotations

from pydantic import BaseModel, Field


class StaffRolePlan(BaseModel):
    """One role the project manager believes should join the project."""

    role: str = Field(description="Model-proposed role label or identifier.")
    title: str = Field(description="Human-readable title for the planned role.")
    responsibilities: list[str] = Field(default_factory=list, description="Responsibility names or descriptions for the role.")
    capabilities: list[str] = Field(default_factory=list, description="Capability names or descriptions needed by the role.")
    task_focus: str = Field(description="Initial task goal this role should focus on.")
    priority: int = Field(default=1, description="Lower numbers should be staffed and executed earlier.")


class StaffingPlan(BaseModel):
    """Project manager's proposed team for reaching the project goal."""

    required_roles: list[StaffRolePlan] = Field(default_factory=list, description="Roles required for the project.")
    rationale: str = Field(description="Why these roles are needed.")


class ProjectResult(BaseModel):
    """Structured project-level output produced by the project manager."""

    summary: str = Field(description="Short summary of the project manager's plan or result.")
    project_understanding: str = Field(description="How the project manager interprets the user goal.")
    assumptions: list[str] = Field(default_factory=list, description="Assumptions made while planning.")
    risks: list[str] = Field(default_factory=list, description="Important risks or uncertainties.")
    staffing_plan: StaffingPlan = Field(description="Recommended staff roles for execution.")
    task_breakdown: list[str] = Field(default_factory=list, description="Major tasks or work packages.")
    execution_plan: list[str] = Field(default_factory=list, description="Ordered plan for completing the project.")
    final_output: str = Field(description="Project manager's final text output for this planning step.")


class TaskExecutionResult(BaseModel):
    """Structured output produced by non-manager staff for one assigned task."""

    summary: str = Field(description="Short summary of the completed task work.")
    work_performed: list[str] = Field(default_factory=list, description="Concrete actions performed by the staff member.")
    deliverables: list[str] = Field(default_factory=list, description="Outputs or artifacts produced by the task.")
    blockers: list[str] = Field(default_factory=list, description="Issues that blocked or limited completion.")
    next_steps: list[str] = Field(default_factory=list, description="Recommended follow-up actions.")
    final_output: str = Field(description="Final text stored as the task result.")


class StaffProfileMatch(BaseModel):
    """How one planned role should become project staff.

    Configured profiles are reusable templates. If no template exists, dynamic
    creation can still build staff directly from the project manager's plan.
    """

    planned_role: str = Field(description="Role value from the project manager's staffing plan.")
    planned_title: str = Field(description="Title value from the project manager's staffing plan.")
    matched: bool = Field(description="Whether this planned role can be turned into staff.")
    source: str = Field(default="profile", description="Creation source: profile, dynamic, or unresolved.")
    profile_name: str | None = Field(default=None, description="Matched configured profile name, if any.")
    profile_role: str | None = Field(default=None, description="Role from the matched configured profile.")
    profile_title: str | None = Field(default=None, description="Title from the matched configured profile.")
    reason: str = Field(description="Human-readable explanation of the match decision.")


class StaffProfileResolution(BaseModel):
    """All configured profile matches for one project staffing plan."""

    matches: list[StaffProfileMatch] = Field(default_factory=list, description="Resolution result for each planned role.")

    @property
    def unresolved(self) -> list[StaffProfileMatch]:
        """Return planned roles that cannot be created from current config."""
        return [match for match in self.matches if not match.matched]
