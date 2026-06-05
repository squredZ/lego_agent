from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, model_validator

logger = logging.getLogger(__name__)


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
    response_format: dict[str, Any] | None = None
    stream: bool = False
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
            "response_format": self.response_format,
            "stream": self.stream,
            "token_limit": self.token_limit,
            "dry_run": self.dry_run,
            **extra,
        }
        return {key: value for key, value in kwargs.items() if value is not None}


class ProjectDefaultsConfig(BaseModel):
    """Project-level defaults shared by all runs using this config."""

    default_manager_profile: str = "project_manager"
    goal: str | None = None


class CliConfig(BaseModel):
    """Default command-line behavior for this runtime config.

    These options keep day-to-day commands short. CLI flags can still override
    them when a run needs a different output shape or log level.
    """

    output_json: bool = False
    include_events: bool = False
    include_staffing_matches: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = None


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


class WorkflowConfig(BaseModel):
    """Selects how each staff member executes an assigned task."""

    type: str = "single_pass"
    max_steps: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=5, ge=0)
    max_output_retries: int = Field(default=2, ge=0)
    fail_on_tool_error: bool = True
    tools: str = "noop"
    enabled_tools: list[str] = Field(default_factory=lambda: ["echo", "read_project_file"])
    workspace_root: str | None = None


class DynamicStaffConfig(BaseModel):
    """Controls staff created from project-manager staffing plans."""

    enabled: bool = True
    default_assistant: AssistantConfig = Field(default_factory=AssistantConfig)
    allow_dynamic_responsibilities: bool = True
    allow_dynamic_capabilities: bool = True


class ProjectRuntimeConfig(BaseModel):
    """Top-level runtime configuration loaded from JSON."""

    project: ProjectDefaultsConfig = Field(default_factory=ProjectDefaultsConfig)
    cli: CliConfig = Field(default_factory=CliConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    staff_profiles: dict[str, StaffProfileConfig]
    dynamic_staff: DynamicStaffConfig = Field(default_factory=DynamicStaffConfig)
    modules: list[str] = Field(default_factory=list)


def load_project_runtime_config(path: Path) -> ProjectRuntimeConfig:
    """Load and validate runtime config from a JSON file."""
    logger.info("loading project runtime config", extra={"config_path": str(path)})
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    config = parse_project_runtime_config(raw)
    logger.info(
        "project runtime config loaded",
        extra={
            "config_path": str(path),
            "staff_profile_count": len(config.staff_profiles),
            "module_count": len(config.modules),
            "orchestration_strategy": config.orchestration.strategy,
        },
    )
    return config


def parse_project_runtime_config(raw: dict[str, Any]) -> ProjectRuntimeConfig:
    """Validate an already-loaded config dictionary."""
    logger.debug("validating project runtime config")
    config = ProjectRuntimeConfig.model_validate(raw)
    logger.debug(
        "project runtime config validated",
        extra={
            "staff_profile_count": len(config.staff_profiles),
            "module_count": len(config.modules),
            "orchestration_strategy": config.orchestration.strategy,
        },
    )
    return config
