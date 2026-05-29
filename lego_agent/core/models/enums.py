from __future__ import annotations

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle state for a project aggregate."""

    CREATED = "created"
    PLANNING = "planning"
    STAFFING = "staffing"
    RUNNING = "running"
    REVIEWING = "reviewing"
    DONE = "done"
    FAILED = "failed"


class TaskStatus(StrEnum):
    """Lifecycle state for one task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class StaffStatus(StrEnum):
    """Working state for one staff member."""

    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    OFFLINE = "offline"


class EventLevel(StrEnum):
    """Severity level for project and task events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
