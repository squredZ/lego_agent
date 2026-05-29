from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    """Describes one tool the assistant may request."""

    name: str = Field(description="Stable tool name used in tool calls.")
    description: str = Field(description="Human-readable explanation of what the tool does.")
    parameters_schema: dict[str, Any] = Field(default_factory=dict, description="JSON schema for tool arguments.")


class ToolCall(BaseModel):
    """One assistant-requested tool invocation."""

    id: str | None = Field(default=None, description="Provider tool call id used to correlate tool results.")
    tool_name: str = Field(description="Name of the requested tool.")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Validated or raw arguments for the tool.")


class ToolResult(BaseModel):
    """Structured result returned after executing a tool call."""

    tool_name: str = Field(description="Name of the tool that was executed.")
    success: bool = Field(description="Whether the tool completed successfully.")
    content: str | None = Field(default=None, description="Text result safe to show to the assistant or user.")
    error: str | None = Field(default=None, description="Error message when the tool failed.")
    data: dict[str, Any] = Field(default_factory=dict, description="Structured tool output for programmatic consumers.")
