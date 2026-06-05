from __future__ import annotations

import logging
from typing import Protocol

from lego_agent.core.models import (
    EventLevel,
    Project,
    Staff,
    StaffMessage,
    StaffMessageType,
    Task,
    TaskStatus,
    WorkResult,
    utc_now,
)
from lego_agent.project.events import EventRecorder

logger = logging.getLogger(__name__)


class TaskStore(Protocol):
    """Persistence boundary for project task state."""

    def create(self, task: Task) -> Task: ...

    def update(self, task: Task) -> Task: ...

    def get(self, task_id: str) -> Task: ...

    def children_of(self, parent_task_id: str) -> list[Task]: ...


class MessageBus(Protocol):
    """Communication boundary for staff notifications."""

    def send(self, message: StaffMessage) -> StaffMessage: ...

    def inbox_for(self, staff_id: str, project_id: str) -> list[StaffMessage]: ...

    def unread_for(self, staff_id: str, project_id: str) -> list[StaffMessage]: ...

    def mark_read(self, message_id: str) -> StaffMessage: ...


class InMemoryTaskStore:
    """Task store backed by a Project aggregate.

    This keeps Version 2A simple while preserving the same interface that a
    future database-backed store should implement.
    """

    def __init__(self, project: Project) -> None:
        self.project = project

    def create(self, task: Task) -> Task:
        if task.id in self.project.tasks:
            raise ValueError(f"task '{task.id}' already exists")
        self.project.tasks[task.id] = task
        logger.info(
            "task stored",
            extra={"project_id": task.project_id, "task_id": task.id, "assigned_to": task.assigned_to},
        )
        return task

    def update(self, task: Task) -> Task:
        if task.id not in self.project.tasks:
            raise KeyError(f"task '{task.id}' does not exist")
        task.updated_at = utc_now()
        self.project.tasks[task.id] = task
        logger.debug(
            "task updated",
            extra={"project_id": task.project_id, "task_id": task.id, "status": task.status.value},
        )
        return task

    def get(self, task_id: str) -> Task:
        try:
            return self.project.tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"task '{task_id}' does not exist") from exc

    def children_of(self, parent_task_id: str) -> list[Task]:
        return [
            task
            for task in self.project.tasks.values()
            if task.parent_task_id == parent_task_id
        ]


class InMemoryMessageBus:
    """Message bus that keeps staff messages in memory."""

    def __init__(self) -> None:
        self._messages: dict[str, StaffMessage] = {}

    def send(self, message: StaffMessage) -> StaffMessage:
        self._messages[message.id] = message
        logger.info(
            "staff message sent",
            extra={
                "project_id": message.project_id,
                "message_id": message.id,
                "message_type": message.type,
                "sender_id": message.sender_id,
                "recipient_id": message.recipient_id,
                "task_id": message.task_id,
            },
        )
        return message

    def inbox_for(self, staff_id: str, project_id: str) -> list[StaffMessage]:
        return [
            message
            for message in self._messages.values()
            if message.project_id == project_id and message.recipient_id == staff_id
        ]

    def unread_for(self, staff_id: str, project_id: str) -> list[StaffMessage]:
        return [
            message
            for message in self.inbox_for(staff_id, project_id)
            if message.read_at is None
        ]

    def mark_read(self, message_id: str) -> StaffMessage:
        try:
            message = self._messages[message_id]
        except KeyError as exc:
            raise KeyError(f"message '{message_id}' does not exist") from exc
        message.read_at = utc_now()
        logger.debug("staff message marked read", extra={"message_id": message_id})
        return message


class TaskDispatcher:
    """Creates assigned child tasks and notifies the assignee."""

    def __init__(
        self,
        task_store: TaskStore,
        message_bus: MessageBus,
        event_recorder: EventRecorder,
    ) -> None:
        self.task_store = task_store
        self.message_bus = message_bus
        self.event_recorder = event_recorder

    def assign(
        self,
        project: Project,
        task: Task,
        assignee: Staff,
        created_by: Staff,
    ) -> Task:
        task.project_id = project.id
        task.assigned_to = assignee.id
        task.created_by = created_by.id
        stored_task = self.task_store.create(task)
        self.event_recorder.project_event(
            project,
            "task_assigned",
            f"Task '{task.title}' assigned to '{assignee.id}'.",
            actor_id=created_by.id,
            task_id=task.id,
        )
        self.event_recorder.task_event(
            task,
            "task_assigned",
            f"Task assigned to '{assignee.id}'.",
            actor_id=created_by.id,
        )
        self.message_bus.send(
            StaffMessage(
                project_id=project.id,
                sender_id=created_by.id,
                recipient_id=assignee.id,
                type=StaffMessageType.TASK_ASSIGNED,
                task_id=task.id,
                content=f"You have been assigned task '{task.title}'.",
            )
        )
        logger.info(
            "task dispatched",
            extra={
                "project_id": project.id,
                "task_id": task.id,
                "created_by": created_by.id,
                "assignee_id": assignee.id,
            },
        )
        return stored_task


class TaskCompletionHandler:
    """Finalizes child task state and notifies the manager."""

    def __init__(
        self,
        task_store: TaskStore,
        message_bus: MessageBus,
        event_recorder: EventRecorder,
    ) -> None:
        self.task_store = task_store
        self.message_bus = message_bus
        self.event_recorder = event_recorder

    def complete(
        self,
        project: Project,
        task: Task,
        staff: Staff,
        result: WorkResult,
    ) -> Task:
        task.status = result.status
        task.result = result.output
        task.error = result.error
        if result.status == TaskStatus.DONE:
            task.completed_at = utc_now()
        updated_task = self.task_store.update(task)

        event_level = EventLevel.ERROR if result.status == TaskStatus.FAILED else EventLevel.INFO
        event_type = "task_failed" if result.status == TaskStatus.FAILED else "task_completed"
        message_type = (
            StaffMessageType.TASK_FAILED
            if result.status == TaskStatus.FAILED
            else StaffMessageType.TASK_COMPLETED
        )
        self.event_recorder.project_event(
            project,
            event_type,
            f"Task '{task.title}' finished with status '{result.status.value}'.",
            level=event_level,
            actor_id=staff.id,
            task_id=task.id,
        )
        self.event_recorder.task_event(
            task,
            event_type,
            f"Task finished with status '{result.status.value}'.",
            level=event_level,
            actor_id=staff.id,
        )
        self.message_bus.send(
            StaffMessage(
                project_id=project.id,
                sender_id=staff.id,
                recipient_id=project.manager_id,
                type=message_type,
                task_id=task.id,
                content=f"Task '{task.title}' finished with status '{result.status.value}'.",
                data={"status": result.status.value},
            )
        )
        self._report_blockers(project, task, staff, result)
        logger.info(
            "task completion handled",
            extra={
                "project_id": project.id,
                "task_id": task.id,
                "staff_id": staff.id,
                "status": result.status.value,
            },
        )
        return updated_task

    def _report_blockers(
        self,
        project: Project,
        task: Task,
        staff: Staff,
        result: WorkResult,
    ) -> None:
        """Notify the manager when structured staff output contains blockers."""
        blockers = result.task_result.blockers if result.task_result else []
        if not blockers:
            return
        message = self.message_bus.send(
            StaffMessage(
                project_id=project.id,
                sender_id=staff.id,
                recipient_id=project.manager_id,
                type=StaffMessageType.BLOCKER_REPORTED,
                task_id=task.id,
                content="\n".join(blockers),
                data={"blocker_count": len(blockers)},
            )
        )
        self.event_recorder.project_event(
            project,
            "staff_blocker_reported",
            f"Staff '{staff.id}' reported {len(blockers)} blocker(s).",
            level=EventLevel.WARNING,
            actor_id=staff.id,
            task_id=task.id,
            data={"message_id": message.id, "blocker_count": len(blockers)},
        )
        logger.info(
            "staff blockers reported",
            extra={
                "project_id": project.id,
                "task_id": task.id,
                "staff_id": staff.id,
                "blocker_count": len(blockers),
            },
        )


class StaffCommunicationService:
    """Business-facing API for staff-to-staff messages.

    Staff members still do not call each other directly. They publish messages
    through MessageBus, and project events make the communication observable.
    """

    def __init__(self, message_bus: MessageBus, event_recorder: EventRecorder) -> None:
        self.message_bus = message_bus
        self.event_recorder = event_recorder

    def send(
        self,
        project: Project,
        sender: Staff,
        recipient: Staff,
        message_type: StaffMessageType,
        content: str,
        *,
        task: Task | None = None,
        data: dict | None = None,
    ) -> StaffMessage:
        """Send one staff message and record a redacted project event."""
        self._validate_staff(project, sender)
        self._validate_staff(project, recipient)
        if task is not None and task.project_id != project.id:
            raise ValueError(f"task '{task.id}' does not belong to project '{project.id}'")

        message = self.message_bus.send(
            StaffMessage(
                project_id=project.id,
                sender_id=sender.id,
                recipient_id=recipient.id,
                type=message_type,
                task_id=task.id if task else None,
                content=content,
                data=data or {},
            )
        )
        self.event_recorder.project_event(
            project,
            "staff_message_sent",
            f"Staff '{sender.id}' sent '{message_type.value}' to '{recipient.id}'.",
            actor_id=sender.id,
            task_id=task.id if task else None,
            data={
                "message_id": message.id,
                "message_type": message_type.value,
                "recipient_id": recipient.id,
            },
        )
        logger.info(
            "staff communication sent",
            extra={
                "project_id": project.id,
                "message_id": message.id,
                "message_type": message_type.value,
                "sender_id": sender.id,
                "recipient_id": recipient.id,
                "task_id": task.id if task else None,
            },
        )
        return message

    def ask_question(
        self,
        project: Project,
        sender: Staff,
        recipient: Staff,
        question: str,
        *,
        task: Task | None = None,
    ) -> StaffMessage:
        """Send a question to another staff member."""
        return self.send(
            project,
            sender,
            recipient,
            StaffMessageType.QUESTION,
            question,
            task=task,
        )

    def request_help(
        self,
        project: Project,
        sender: Staff,
        recipient: Staff,
        request: str,
        *,
        task: Task | None = None,
    ) -> StaffMessage:
        """Ask another staff member for support without changing task state."""
        return self.send(
            project,
            sender,
            recipient,
            StaffMessageType.HELP_REQUESTED,
            request,
            task=task,
        )

    def report_blocker(
        self,
        project: Project,
        sender: Staff,
        recipient: Staff,
        blocker: str,
        *,
        task: Task | None = None,
    ) -> StaffMessage:
        """Notify another staff member about a blocker or unresolved issue."""
        return self.send(
            project,
            sender,
            recipient,
            StaffMessageType.BLOCKER_REPORTED,
            blocker,
            task=task,
        )

    def _validate_staff(self, project: Project, staff: Staff) -> None:
        if staff.project_id != project.id or staff.id not in project.staff:
            raise ValueError(f"staff '{staff.id}' does not belong to project '{project.id}'")
