from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from lego_agent.core.models.base import new_id, utc_now


class MemoryItem(BaseModel):
    """A reusable memory entry available to workflow memory managers."""

    id: str = Field(default_factory=new_id, description="Unique memory item id.")
    scope: str = Field(description="Memory scope, such as project, staff, or global.")
    content: str = Field(description="Memory text content.")
    tags: list[str] = Field(default_factory=list, description="Search or filtering tags.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Structured metadata for storage or retrieval.")
    created_at: datetime = Field(default_factory=utc_now, description="Timestamp when the memory item was created.")
