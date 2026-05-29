from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """One model conversation message passed to an assistant provider."""

    role: str = Field(description="Message role such as system, user, assistant, or tool.")
    content: str = Field(description="Message text content.")


class OutputContract(BaseModel):
    """Describes the structured output expected from an assistant."""

    name: str = Field(description="Human-readable contract name, such as ProjectResult.")
    json_schema: dict[str, Any] = Field(description="JSON schema used to validate assistant output.")
    instructions: str = Field(description="Prompt instructions describing how to satisfy the contract.")


class AssistantResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    content: str = Field(description="Assistant text content extracted from the provider response.")
    structured: dict[str, Any] = Field(default_factory=dict, description="Optional provider- or parser-produced structured data.")
    raw: Any | None = Field(default=None, description="Raw provider response for debugging or advanced adapters.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Adapter-specific response metadata.")


@runtime_checkable
class Assistant(Protocol):
    """Common interface implemented by model provider adapters."""

    def respond(self, request: Any) -> AssistantResponse:
        """Return an assistant response for a staff workflow request."""
