from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProjectError(BaseModel):
    """Structured error stored when a project run fails."""

    type: str = Field(description="Stable error type, usually an exception or domain error name.")
    message: str = Field(description="Human-readable error message.")
    retryable: bool = Field(default=False, description="Whether retrying the project may reasonably succeed.")
    details: dict[str, Any] = Field(default_factory=dict, description="Structured diagnostic details safe to expose.")


class TaskError(BaseModel):
    """Structured error stored when a task workflow fails."""

    type: str = Field(description="Stable error type, usually an exception or domain error name.")
    message: str = Field(description="Human-readable error message.")
    retryable: bool = Field(default=False, description="Whether retrying the task may reasonably succeed.")
    details: dict[str, Any] = Field(default_factory=dict, description="Structured diagnostic details safe to expose.")
