from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from lego_agent.core.models.base import new_id, utc_now
from lego_agent.core.models.enums import EventLevel


class ProjectEvent(BaseModel):
    """Observable event emitted at project scope."""

    id: str = Field(default_factory=new_id, description="Unique event id.")
    project_id: str = Field(description="Project this event belongs to.")
    type: str = Field(description="Stable event type used by logs, tests, and UI.")
    message: str = Field(description="Human-readable event message.")
    level: EventLevel = Field(default=EventLevel.INFO, description="Event severity.")
    actor_id: str | None = Field(default=None, description="Staff or system actor that caused the event.")
    task_id: str | None = Field(default=None, description="Related task id, if the event is task-specific.")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured event metadata.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp when the event was created.")


class TaskEvent(BaseModel):
    """Observable event emitted for one task."""

    id: str = Field(default_factory=new_id, description="Unique event id.")
    project_id: str = Field(description="Project this task event belongs to.")
    task_id: str = Field(description="Task this event belongs to.")
    type: str = Field(description="Stable event type used by logs, tests, and UI.")
    message: str = Field(description="Human-readable event message.")
    level: EventLevel = Field(default=EventLevel.INFO, description="Event severity.")
    actor_id: str | None = Field(default=None, description="Staff or system actor that caused the event.")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured event metadata.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp when the event was created.")
