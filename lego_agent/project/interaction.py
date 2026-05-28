from __future__ import annotations

import logging
from typing import Protocol

from lego_agent.core.models import (
    EventLevel,
    Project,
    Staff,
    StaffMessage,
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
                type="task_assigned",
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
                type=event_type,
                task_id=task.id,
                content=f"Task '{task.title}' finished with status '{result.status.value}'.",
                data={"status": result.status.value},
            )
        )
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
