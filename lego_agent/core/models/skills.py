from __future__ import annotations

from pydantic import BaseModel, Field


class SkillSpec(BaseModel):
    """Reusable work method selected for a staff task."""

    name: str = Field(description="Stable skill name.")
    description: str = Field(description="Human-readable summary of the skill.")
    instructions: str = Field(description="Prompt instructions that teach the staff member how to apply the skill.")
    required_capabilities: list[str] = Field(default_factory=list, description="Capability names expected for this skill.")
    available_tools: list[str] = Field(default_factory=list, description="Tool names this skill is allowed or expected to use.")
