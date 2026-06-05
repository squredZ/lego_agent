from __future__ import annotations

import logging
from pathlib import Path

from lego_agent.core.models import (
    MemoryItem,
    Project,
    SkillSpec,
    Staff,
    Task,
    ToolCall,
    ToolResult,
    ToolSpec,
    WorkContext,
)
from lego_agent.workflow.tools import ToolRegistry, create_builtin_tool_registry

logger = logging.getLogger(__name__)


class DefaultContextManager:
    """Builds the minimal context needed by Version 1.

    Context is intentionally a separate object instead of being stored on Staff.
    Each task run can build different context from the same project and staff.
    """

    def build_context(self, project: Project, staff: Staff, task: Task) -> WorkContext:
        logger.debug(
            "building work context",
            extra={"project_id": project.id, "staff_id": staff.id, "task_id": task.id},
        )
        responsibilities = ", ".join(item.name for item in staff.responsibilities)
        capabilities = ", ".join(item.name for item in staff.capabilities)
        return WorkContext(
            project_id=project.id,
            task_id=task.id,
            staff_id=staff.id,
            project_goal=project.goal,
            task_goal=task.goal,
            role_context=(
                f"role={staff.role}; title={staff.title}; "
                f"responsibilities={responsibilities or 'none'}; "
                f"capabilities={capabilities or 'none'}"
            ),
            task_context=task.title,
        )


class NoopMemoryManager:
    """Memory interface placeholder.

    This makes memory a stable workflow slot without introducing storage,
    retrieval, or vector search in the first version.
    """

    def retrieve(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        query: str,
    ) -> list[MemoryItem]:
        logger.debug(
            "noop memory retrieve",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "task_id": task.id,
                "query_length": len(query),
            },
        )
        return []

    def remember(self, project: Project, staff: Staff, item: MemoryItem) -> None:
        logger.debug(
            "noop memory remember",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "scope": item.scope,
                "tag_count": len(item.tags),
            },
        )
        return None


class NoopToolManager:
    """Tool interface placeholder.

    Version 1 can describe where tools will fit, but assistant-requested tool
    execution is intentionally disabled.
    """

    def list_tools(self, staff: Staff, task: Task) -> list[ToolSpec]:
        logger.debug(
            "noop tool list",
            extra={"project_id": task.project_id, "staff_id": staff.id, "task_id": task.id},
        )
        return []

    def call_tool(self, call: ToolCall) -> ToolResult:
        logger.warning("tool call rejected because tools are disabled", extra={"tool_name": call.tool_name})
        return ToolResult(
            tool_name=call.tool_name,
            success=False,
            error="tool execution is not enabled in version 1",
        )


class BuiltinToolManager:
    """Executes registered built-in tools through one controlled boundary.

    The manager is responsible for workflow-facing policy: which tools are
    enabled, how calls are logged, and how unknown or disabled calls fail. The
    concrete tool behavior lives in Tool classes registered in ToolRegistry.
    """

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        enabled_tools: list[str] | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.registry = registry or create_builtin_tool_registry(workspace_root=workspace_root)
        self.enabled_tools = set(enabled_tools or self.registry.names())

    def list_tools(self, staff: Staff, task: Task) -> list[ToolSpec]:
        logger.debug(
            "builtin tool list",
            extra={
                "project_id": task.project_id,
                "staff_id": staff.id,
                "task_id": task.id,
                "tool_count": len(self.enabled_tools),
            },
        )
        return self.registry.list_specs(self.enabled_tools)

    def call_tool(self, call: ToolCall) -> ToolResult:
        logger.info("builtin tool call started", extra={"tool_name": call.tool_name})
        if call.tool_name not in self.enabled_tools:
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error=f"tool '{call.tool_name}' is not enabled",
            )
        return self.registry.call(call)


class NoopSkillManager:
    """Skill interface placeholder.

    Skills are reusable work methods. Version 1 does not execute nested skill
    runtimes, so this manager returns no selected skills.
    """

    def list_skills(self, staff: Staff, task: Task) -> list[SkillSpec]:
        logger.debug(
            "noop skill list",
            extra={"project_id": task.project_id, "staff_id": staff.id, "task_id": task.id},
        )
        return []

    def select_skills(
        self,
        staff: Staff,
        task: Task,
        context: WorkContext,
    ) -> list[SkillSpec]:
        logger.debug(
            "noop skill select",
            extra={
                "project_id": context.project_id,
                "staff_id": staff.id,
                "task_id": task.id,
            },
        )
        return []
