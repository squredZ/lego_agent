from __future__ import annotations

import logging

from lego_agent.core.models import (
    EventLevel,
    Project,
    ProjectError,
    ProjectRunResult,
    ProjectStatus,
    TaskStatus,
    utc_now,
)
from lego_agent.project.events import EventRecorder
from lego_agent.workflow.staff_workflow import SinglePassStaffWorkflow

logger = logging.getLogger(__name__)


class ProjectManagerOnlyOrchestrator:
    """Version 1 project orchestrator.

    This orchestrator deliberately runs only the primary project manager. The
    manager can output a staffing plan, but recruited staff are not created or
    executed until the next development phase.
    """

    def __init__(
        self,
        workflow: SinglePassStaffWorkflow,
        event_recorder: EventRecorder | None = None,
    ) -> None:
        self.workflow = workflow
        self.event_recorder = event_recorder or workflow.event_recorder

    def run(self, project: Project) -> ProjectRunResult:
        """Execute the manager task and translate workflow output to run output."""
        started_at = utc_now()
        project.status = ProjectStatus.PLANNING
        manager = project.manager
        # Version 1 creates exactly one task: the project manager planning task.
        task = next(iter(project.tasks.values()))
        logger.info(
            "project manager orchestration started",
            extra={
                "project_id": project.id,
                "manager_id": manager.id,
                "task_id": task.id,
            },
        )
        self.event_recorder.project_event(
            project,
            "project_planning_started",
            "Project manager planning started.",
            actor_id=manager.id,
            task_id=task.id,
        )

        work_result = self.workflow.run(project, manager, task)
        completed_at = utc_now()

        if work_result.status == TaskStatus.DONE and work_result.project_result is not None:
            # Keep the project aggregate in sync with the successful work result.
            project.status = ProjectStatus.DONE
            project.result = work_result.project_result
            project.staffing_plan = work_result.project_result.staffing_plan
            project.completed_at = completed_at
            logger.info(
                "project manager orchestration completed",
                extra={
                    "project_id": project.id,
                    "manager_id": manager.id,
                    "task_id": task.id,
                    "status": project.status.value,
                },
            )
            self.event_recorder.project_event(
                project,
                "project_completed",
                "Project manager only run completed successfully.",
                actor_id=manager.id,
                task_id=task.id,
            )
            return ProjectRunResult(
                project_id=project.id,
                project_goal=project.goal,
                status=project.status,
                manager_id=manager.id,
                manager_name=manager.name,
                result=project.result,
                events=project.events,
                started_at=started_at,
                completed_at=completed_at,
            )

        project.status = ProjectStatus.FAILED
        project.error = ProjectError(
            type=work_result.error.type if work_result.error else "WorkflowError",
            message=work_result.error.message if work_result.error else "workflow did not produce a project result",
        )
        project.completed_at = completed_at
        logger.error(
            "project manager orchestration failed",
            extra={
                "project_id": project.id,
                "manager_id": manager.id,
                "task_id": task.id,
                "error_type": project.error.type,
            },
        )
        self.event_recorder.project_event(
            project,
            "project_failed",
            project.error.message,
            level=EventLevel.ERROR,
            actor_id=manager.id,
            task_id=task.id,
        )
        return ProjectRunResult(
            project_id=project.id,
            project_goal=project.goal,
            status=project.status,
            manager_id=manager.id,
            manager_name=manager.name,
            error=project.error,
            events=project.events,
            started_at=started_at,
            completed_at=completed_at,
        )
