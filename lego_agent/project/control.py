from __future__ import annotations

import logging

from lego_agent.core.models import (
    EventLevel,
    ManagerAction,
    ManagerDecision,
    Project,
    ProjectSnapshot,
    ProjectStatus,
    Staff,
    StaffMessage,
    StaffMessageSnapshot,
    StaffMessageType,
    StaffSnapshot,
    Task,
    TaskSnapshot,
    TaskStatus,
)
from lego_agent.project.events import EventRecorder
from lego_agent.project.interaction import MessageBus

logger = logging.getLogger(__name__)


class ManagerControlLoop:
    """Synchronous project-manager decision loop.

    This first implementation deliberately uses deterministic rules. It creates
    the stable boundary the future LLM-based manager loop should use: collect a
    read-only snapshot, produce a ManagerDecision, and let the orchestrator
    apply that decision.
    """

    def __init__(self, event_recorder: EventRecorder) -> None:
        self.event_recorder = event_recorder

    def decide(
        self,
        project: Project,
        manager: Staff,
        tasks: list[Task],
        message_bus: MessageBus,
    ) -> ManagerDecision:
        """Collect project state and return the next manager decision."""
        snapshot = self.snapshot(project, manager, tasks, message_bus)
        decision = self._rule_based_decision(snapshot)
        self._record_decision(project, manager, decision)
        return decision

    def snapshot(
        self,
        project: Project,
        manager: Staff,
        tasks: list[Task],
        message_bus: MessageBus,
    ) -> ProjectSnapshot:
        """Build the read-only state a manager can use for decisions."""
        unread_messages = message_bus.unread_for(manager.id, project.id)
        snapshot = ProjectSnapshot(
            project_id=project.id,
            project_status=project.status,
            manager_id=manager.id,
            tasks=[self._task_snapshot(task) for task in tasks],
            staff=[self._staff_snapshot(staff) for staff in project.staff.values()],
            unread_manager_message_count=len(unread_messages),
            unread_manager_messages=[
                self._message_snapshot(message)
                for message in unread_messages
            ],
            event_count=len(project.events),
        )
        logger.debug(
            "manager control snapshot collected",
            extra={
                "project_id": project.id,
                "manager_id": manager.id,
                "task_count": len(snapshot.tasks),
                "staff_count": len(snapshot.staff),
                "unread_manager_message_count": snapshot.unread_manager_message_count,
            },
        )
        return snapshot

    def _rule_based_decision(self, snapshot: ProjectSnapshot) -> ManagerDecision:
        """Return a conservative decision from task state.

        The rule order mirrors project-management priority: failed work blocks
        review, unfinished work means wait, and only fully completed work moves
        to manager review.
        """
        task_ids = [task.task_id for task in snapshot.tasks]
        if not snapshot.tasks:
            return ManagerDecision(
                action=ManagerAction.REVIEW,
                rationale="No child tasks exist, so the manager should review the project plan directly.",
                project_status=ProjectStatus.REVIEWING,
                task_ids=[],
            )
        failed_tasks = [task.task_id for task in snapshot.tasks if task.status == TaskStatus.FAILED]
        if failed_tasks:
            return ManagerDecision(
                action=ManagerAction.FAIL,
                rationale="One or more child tasks failed and require project failure handling.",
                project_status=ProjectStatus.FAILED,
                task_ids=failed_tasks,
            )
        manager_attention_messages = [
            message
            for message in snapshot.unread_manager_messages
            if message.type
            in {
                StaffMessageType.BLOCKER_REPORTED,
                StaffMessageType.HELP_REQUESTED,
                StaffMessageType.QUESTION,
            }
        ]
        if manager_attention_messages:
            task_ids = [
                message.task_id
                for message in manager_attention_messages
                if message.task_id is not None
            ]
            return ManagerDecision(
                action=ManagerAction.ASK_USER,
                rationale="Unread staff messages require manager or user clarification before review.",
                project_status=snapshot.project_status,
                task_ids=task_ids,
            )
        unfinished_tasks = [
            task.task_id
            for task in snapshot.tasks
            if task.status in {TaskStatus.PENDING, TaskStatus.IN_PROGRESS}
        ]
        if unfinished_tasks:
            return ManagerDecision(
                action=ManagerAction.WAIT,
                rationale="Some child tasks are not complete yet.",
                project_status=snapshot.project_status,
                task_ids=unfinished_tasks,
            )
        return ManagerDecision(
            action=ManagerAction.REVIEW,
            rationale="All child tasks are complete and ready for manager review.",
            project_status=ProjectStatus.REVIEWING,
            task_ids=task_ids,
        )

    def _record_decision(self, project: Project, manager: Staff, decision: ManagerDecision) -> None:
        """Record decisions without leaking task results or message content."""
        level = EventLevel.ERROR if decision.action == ManagerAction.FAIL else EventLevel.INFO
        self.event_recorder.project_event(
            project,
            "manager_decision_made",
            f"Manager decision: {decision.action.value}.",
            level=level,
            actor_id=manager.id,
            data={
                "action": decision.action.value,
                "task_ids": decision.task_ids,
                "project_status": decision.project_status.value if decision.project_status else None,
            },
        )
        logger.info(
            "manager decision made",
            extra={
                "project_id": project.id,
                "manager_id": manager.id,
                "action": decision.action.value,
                "task_count": len(decision.task_ids),
            },
        )

    def _task_snapshot(self, task: Task) -> TaskSnapshot:
        return TaskSnapshot(
            task_id=task.id,
            title=task.title,
            assigned_to=task.assigned_to,
            status=task.status,
            has_result=task.result is not None,
            has_error=task.error is not None,
        )

    def _staff_snapshot(self, staff: Staff) -> StaffSnapshot:
        return StaffSnapshot(
            staff_id=staff.id,
            role=staff.role,
            title=staff.title,
            status=staff.status,
            current_task_id=staff.current_task_id,
        )

    def _message_snapshot(self, message: StaffMessage) -> StaffMessageSnapshot:
        return StaffMessageSnapshot(
            message_id=message.id,
            sender_id=message.sender_id,
            recipient_id=message.recipient_id,
            type=message.type,
            task_id=message.task_id,
            content_summary=self._summarize_message_content(message.content),
        )

    def _summarize_message_content(self, content: str) -> str:
        """Keep manager-facing message context short and predictable."""
        normalized = " ".join(content.split())
        if len(normalized) <= 160:
            return normalized
        return f"{normalized[:157]}..."
