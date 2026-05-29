from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Responsibility(BaseModel):
    """A responsibility describes what a staff member is accountable for."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Stable responsibility name used in config and prompts.")
    description: str = Field(description="Human-readable explanation of the responsibility.")


class Capability(BaseModel):
    """A capability describes what a staff member is able to do."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Stable capability name used in config and prompts.")
    description: str = Field(description="Human-readable explanation of the capability.")
