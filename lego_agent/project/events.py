from __future__ import annotations

import logging
from typing import Any

from lego_agent.core.models import EventLevel, Project, ProjectEvent, Task, TaskEvent

logger = logging.getLogger(__name__)


class EventRecorder:
    """In-memory event recorder for project and task activity.

    This is deliberately small: it appends events to the current Project/Task
    objects so tests and CLI/API layers can inspect what happened during a run.
    A future persistent store can implement the same behavior behind this class.
    """

    def project_event(
        self,
        project: Project,
        event_type: str,
        message: str,
        *,
        level: EventLevel = EventLevel.INFO,
        actor_id: str | None = None,
        task_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> ProjectEvent:
        event = ProjectEvent(
            project_id=project.id,
            type=event_type,
            message=message,
            level=level,
            actor_id=actor_id,
            task_id=task_id,
            data=data or {},
        )
        project.events.append(event)
        logger.log(
            _logging_level(level),
            "project event recorded: %s",
            event_type,
            extra={
                "project_id": project.id,
                "event_type": event_type,
                "actor_id": actor_id,
                "task_id": task_id,
            },
        )
        return event

    def task_event(
        self,
        task: Task,
        event_type: str,
        message: str,
        *,
        level: EventLevel = EventLevel.INFO,
        actor_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> TaskEvent:
        event = TaskEvent(
            project_id=task.project_id,
            task_id=task.id,
            type=event_type,
            message=message,
            level=level,
            actor_id=actor_id,
            data=data or {},
        )
        task.events.append(event)
        logger.log(
            _logging_level(level),
            "task event recorded: %s",
            event_type,
            extra={
                "project_id": task.project_id,
                "task_id": task.id,
                "event_type": event_type,
                "actor_id": actor_id,
            },
        )
        return event


def _logging_level(level: EventLevel) -> int:
    """Map framework event levels to standard logging levels."""
    if level == EventLevel.ERROR:
        return logging.ERROR
    if level == EventLevel.WARNING:
        return logging.WARNING
    return logging.INFO
