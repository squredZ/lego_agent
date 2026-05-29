from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from lego_agent.core.models.base import new_id, utc_now


class StaffMessage(BaseModel):
    """Notification sent between staff through a message bus.

    Staff should not call each other directly. Messages are lightweight
    notifications; task state remains the source of truth.
    """

    id: str = Field(default_factory=new_id, description="Unique message id.")
    project_id: str = Field(description="Project this message belongs to.")
    sender_id: str = Field(description="Staff or system actor that sent the message.")
    recipient_id: str = Field(description="Staff id that should receive the message.")
    type: str = Field(description="Message type such as task_assigned or task_completed.")
    content: str = Field(description="Human-readable message body.")
    task_id: str | None = Field(default=None, description="Related task id, if any.")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured message metadata.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp when the message was sent.")
    read_at: datetime | None = Field(default=None, description="Timestamp when the recipient marked the message as read.")


class StaffInbox(BaseModel):
    """Unread and historical messages for one staff member in one project."""

    staff_id: str = Field(description="Staff id that owns this inbox.")
    project_id: str = Field(description="Project this inbox belongs to.")
    messages: list[StaffMessage] = Field(default_factory=list, description="Messages delivered to this inbox.")

    @property
    def unread(self) -> list[StaffMessage]:
        """Return messages that have not been marked read."""
        return [message for message in self.messages if message.read_at is None]
