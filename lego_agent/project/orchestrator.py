from __future__ import annotations

from lego_agent.core.models import (
    Project,
    ProjectError,
    ProjectRunResult,
    ProjectStatus,
    TaskStatus,
    utc_now,
)
from lego_agent.workflow.staff_workflow import SinglePassStaffWorkflow


class ProjectManagerOnlyOrchestrator:
    """Version 1 project orchestrator.

    This orchestrator deliberately runs only the primary project manager. The
    manager can output a staffing plan, but recruited staff are not created or
    executed until the next development phase.
    """

    def __init__(self, workflow: SinglePassStaffWorkflow) -> None:
        self.workflow = workflow

    def run(self, project: Project) -> ProjectRunResult:
        """Execute the manager task and translate workflow output to run output."""
        started_at = utc_now()
        project.status = ProjectStatus.PLANNING
        manager = project.manager
        # Version 1 creates exactly one task: the project manager planning task.
        task = next(iter(project.tasks.values()))

        work_result = self.workflow.run(project, manager, task)
        completed_at = utc_now()

        if work_result.status == TaskStatus.DONE and work_result.project_result is not None:
            # Keep the project aggregate in sync with the successful work result.
            project.status = ProjectStatus.DONE
            project.result = work_result.project_result
            project.staffing_plan = work_result.project_result.staffing_plan
            project.completed_at = completed_at
            return ProjectRunResult(
                project_id=project.id,
                project_goal=project.goal,
                status=project.status,
                manager_id=manager.id,
                manager_name=manager.name,
                result=project.result,
                started_at=started_at,
                completed_at=completed_at,
            )

        project.status = ProjectStatus.FAILED
        project.error = ProjectError(
            type=work_result.error.type if work_result.error else "WorkflowError",
            message=work_result.error.message if work_result.error else "workflow did not produce a project result",
        )
        project.completed_at = completed_at
        return ProjectRunResult(
            project_id=project.id,
            project_goal=project.goal,
            status=project.status,
            manager_id=manager.id,
            manager_name=manager.name,
            error=project.error,
            started_at=started_at,
            completed_at=completed_at,
        )
