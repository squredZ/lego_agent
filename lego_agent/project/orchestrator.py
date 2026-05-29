from __future__ import annotations

import logging

from lego_agent.core.models import (
    EventLevel,
    Project,
    ProjectError,
    ProjectRunResult,
    ProjectStatus,
    Staff,
    StaffRolePlan,
    Task,
    TaskStatus,
    utc_now,
)
from lego_agent.project.events import EventRecorder
from lego_agent.project.interaction import (
    InMemoryMessageBus,
    InMemoryTaskStore,
    TaskCompletionHandler,
    TaskDispatcher,
)
from lego_agent.project.staffing import StaffFactory, normalize_staff_role_id
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


class ProjectManagerWithStaffOrchestrator:
    """Version 2A bootstrap orchestrator for PM-led staffing.

    This strategy runs the project manager, creates recruited staff from the
    resulting staffing plan, assigns one child task to each recruited staff
    member, then executes those child tasks synchronously. Manager review is
    still a later phase, so a successful run ends in `REVIEWING`.
    """

    def __init__(
        self,
        workflow: SinglePassStaffWorkflow,
        staff_factory: StaffFactory,
        event_recorder: EventRecorder | None = None,
    ) -> None:
        self.workflow = workflow
        self.staff_factory = staff_factory
        self.event_recorder = event_recorder or workflow.event_recorder

    def run(self, project: Project) -> ProjectRunResult:
        """Run PM planning, then create recruited staff and child tasks."""
        started_at = utc_now()
        project.status = ProjectStatus.PLANNING
        manager = project.manager
        manager_task = next(iter(project.tasks.values()))
        logger.info(
            "project manager with staff orchestration started",
            extra={
                "project_id": project.id,
                "manager_id": manager.id,
                "task_id": manager_task.id,
            },
        )
        self.event_recorder.project_event(
            project,
            "project_planning_started",
            "Project manager planning started.",
            actor_id=manager.id,
            task_id=manager_task.id,
        )

        work_result = self.workflow.run(project, manager, manager_task)
        if work_result.status != TaskStatus.DONE or work_result.project_result is None:
            completed_at = utc_now()
            return self._failed_result(project, manager_task, work_result, started_at, completed_at)

        project.result = work_result.project_result
        project.staffing_plan = work_result.project_result.staffing_plan
        project.status = ProjectStatus.STAFFING
        task_store = InMemoryTaskStore(project)
        message_bus = InMemoryMessageBus()
        child_tasks = self._create_recruited_staff_and_tasks(
            project,
            manager,
            manager_task,
            TaskDispatcher(task_store, message_bus, self.event_recorder),
        )
        self.event_recorder.project_event(
            project,
            "project_staffing_completed",
            "Recruited staff and child tasks created from staffing plan.",
            actor_id=manager.id,
            task_id=manager_task.id,
            data={
                "staff_count": len(project.staff) - 1,
                "task_count": len(project.tasks) - 1,
            },
        )
        self._execute_child_tasks(
            project,
            child_tasks,
            TaskCompletionHandler(task_store, message_bus, self.event_recorder),
        )
        completed_at = utc_now()
        if any(task.status == TaskStatus.FAILED for task in child_tasks):
            project.status = ProjectStatus.FAILED
            project.error = ProjectError(
                type="ChildTaskFailed",
                message="one or more recruited staff tasks failed",
            )
            project.completed_at = completed_at
            self.event_recorder.project_event(
                project,
                "project_failed",
                project.error.message,
                level=EventLevel.ERROR,
                actor_id=manager.id,
                task_id=manager_task.id,
            )
        else:
            project.status = ProjectStatus.REVIEWING
            # The CLI run has finished, but the project has not. `Project.completed_at`
            # is reserved for terminal states such as DONE or FAILED.
            self.event_recorder.project_event(
                project,
                "project_ready_for_review",
                "All recruited staff tasks completed and await manager review.",
                actor_id=manager.id,
                task_id=manager_task.id,
                data={"completed_child_task_count": len(child_tasks)},
            )
        logger.info(
            "project manager with staff orchestration completed worker execution",
            extra={
                "project_id": project.id,
                "status": project.status.value,
                "staff_count": len(project.staff),
                "task_count": len(project.tasks),
            },
        )
        return ProjectRunResult(
            project_id=project.id,
            project_goal=project.goal,
            status=project.status,
            manager_id=manager.id,
            manager_name=manager.name,
            result=project.result,
            error=project.error,
            events=project.events,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _create_recruited_staff_and_tasks(
        self,
        project: Project,
        manager: Staff,
        manager_task: Task,
        dispatcher: TaskDispatcher,
    ) -> list[Task]:
        child_tasks: list[Task] = []
        if project.staffing_plan is None:
            raise ValueError("project staffing plan is missing")
        for role_plan in sorted(project.staffing_plan.required_roles, key=lambda item: item.priority):
            if normalize_staff_role_id(role_plan.role) == project.manager.role:
                logger.warning(
                    "skipping staffing plan role because it matches project manager",
                    extra={"project_id": project.id, "role": role_plan.role},
                )
                continue
            staff = self.staff_factory.create_from_plan(
                role_plan,
                project.id,
                manager_id=project.manager_id,
            )
            project.staff[staff.id] = staff
            self.event_recorder.project_event(
                project,
                "staff_created",
                f"Staff '{staff.id}' created from staffing plan.",
                actor_id=manager.id,
                data={"role": staff.role, "title": staff.title},
            )
            child_task = dispatcher.assign(
                project,
                self._task_from_role_plan(project, manager_task, role_plan),
                staff,
                manager,
            )
            child_tasks.append(child_task)
        return child_tasks

    def _execute_child_tasks(
        self,
        project: Project,
        child_tasks: list[Task],
        completion_handler: TaskCompletionHandler,
    ) -> None:
        """Execute recruited staff tasks one by one through the same workflow."""
        project.status = ProjectStatus.RUNNING
        for task in child_tasks:
            if task.assigned_to is None:
                raise ValueError(f"child task '{task.id}' is missing an assignee")
            staff = project.staff[task.assigned_to]
            logger.info(
                "executing recruited staff task",
                extra={
                    "project_id": project.id,
                    "staff_id": staff.id,
                    "task_id": task.id,
                },
            )
            self.event_recorder.project_event(
                project,
                "child_task_execution_started",
                f"Recruited staff '{staff.id}' started task '{task.title}'.",
                actor_id=staff.id,
                task_id=task.id,
            )
            work_result = self.workflow.run(project, staff, task)
            completion_handler.complete(project, task, staff, work_result)

    def _task_from_role_plan(
        self,
        project: Project,
        manager_task: Task,
        role_plan: StaffRolePlan,
    ) -> Task:
        return Task(
            project_id=project.id,
            title=f"{role_plan.title} task",
            goal=role_plan.task_focus,
            parent_task_id=manager_task.id,
        )

    def _failed_result(
        self,
        project: Project,
        manager_task: Task,
        work_result,
        started_at,
        completed_at,
    ) -> ProjectRunResult:
        manager = project.manager
        project.status = ProjectStatus.FAILED
        project.error = ProjectError(
            type=work_result.error.type if work_result.error else "WorkflowError",
            message=work_result.error.message if work_result.error else "workflow did not produce a project result",
        )
        project.completed_at = completed_at
        self.event_recorder.project_event(
            project,
            "project_failed",
            project.error.message,
            level=EventLevel.ERROR,
            actor_id=manager.id,
            task_id=manager_task.id,
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
