from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, model_validator


class AssistantConfig(BaseModel):
    """Configuration for an OpenAI-compatible assistant.

    `extra="allow"` keeps the config forward-compatible with provider-specific
    options. Known options are mapped explicitly in `to_assistant_kwargs`.
    """

    model_config = ConfigDict(extra="allow")

    type: str = "openai"
    options: dict[str, Any] = Field(default_factory=dict)
    model: str = "gpt-4.1-mini"
    api_key: SecretStr | None = None
    base_url: str | None = None
    timeout_seconds: float | None = None
    thinking: dict[str, Any] | None = None
    reasoning_effort: str | None = None
    token_limit: int | None = Field(
        default=None,
        validation_alias=AliasChoices("token_limit", "tokenlimit", "max_output_tokens"),
    )
    dry_run: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def merge_legacy_options(cls, raw: Any) -> Any:
        """Accept both flat config and older nested `options` config."""
        if not isinstance(raw, dict):
            return raw
        options = raw.get("options")
        if not isinstance(options, dict):
            return raw
        merged = {**options, **{key: value for key, value in raw.items() if key != "options"}}
        merged["options"] = options
        return merged

    def to_assistant_kwargs(self) -> dict[str, Any]:
        """Convert validated config to constructor kwargs for assistant classes."""
        extra = self.model_extra or {}
        kwargs = {
            "model": self.model,
            "api_key": self.api_key.get_secret_value() if self.api_key else None,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "thinking": self.thinking,
            "reasoning_effort": self.reasoning_effort,
            "token_limit": self.token_limit,
            "dry_run": self.dry_run,
            **extra,
        }
        return {key: value for key, value in kwargs.items() if value is not None}


class ProjectDefaultsConfig(BaseModel):
    """Project-level defaults shared by all runs using this config."""

    default_manager_profile: str = "project_manager"


class StaffProfileConfig(BaseModel):
    """Reusable recipe for creating a Staff member."""

    name: str
    role: str
    title: str
    description: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    assistant: AssistantConfig = Field(default_factory=AssistantConfig)


class OrchestrationConfig(BaseModel):
    """Selects the project orchestration strategy."""

    strategy: str = "project_manager_only"


class ProjectRuntimeConfig(BaseModel):
    """Top-level runtime configuration loaded from JSON."""

    project: ProjectDefaultsConfig = Field(default_factory=ProjectDefaultsConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    staff_profiles: dict[str, StaffProfileConfig]
    modules: list[str] = Field(default_factory=list)


def load_project_runtime_config(path: Path) -> ProjectRuntimeConfig:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    return parse_project_runtime_config(raw)


def parse_project_runtime_config(raw: dict[str, Any]) -> ProjectRuntimeConfig:
    return ProjectRuntimeConfig.model_validate(raw)
