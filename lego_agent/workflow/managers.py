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
    """Executes small built-in tools through one controlled boundary.

    The first tools intentionally follow a narrow Codex-style shape: explicit
    schemas, workspace safety for file reads, structured ToolResult values, and
    no direct workflow access to implementation details.
    """

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        enabled_tools: list[str] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.enabled_tools = set(enabled_tools or ["echo", "read_project_file"])

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
        specs = {
            "echo": ToolSpec(
                name="echo",
                description="Return the provided text. Useful for deterministic tool-loop tests.",
                parameters_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            ),
            "read_project_file": ToolSpec(
                name="read_project_file",
                description="Read a UTF-8 text file inside the current workspace.",
                parameters_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
        }
        return [spec for name, spec in specs.items() if name in self.enabled_tools]

    def call_tool(self, call: ToolCall) -> ToolResult:
        logger.info("builtin tool call started", extra={"tool_name": call.tool_name})
        if call.tool_name not in self.enabled_tools:
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error=f"tool '{call.tool_name}' is not enabled",
            )
        if call.tool_name == "echo":
            return self._echo(call)
        if call.tool_name == "read_project_file":
            return self._read_project_file(call)
        return ToolResult(
            tool_name=call.tool_name,
            success=False,
            error=f"tool '{call.tool_name}' is not implemented",
        )

    def _echo(self, call: ToolCall) -> ToolResult:
        text = call.arguments.get("text", "")
        content = str(text)
        logger.info("builtin echo completed", extra={"content_length": len(content)})
        return ToolResult(tool_name=call.tool_name, success=True, content=content)

    def _read_project_file(self, call: ToolCall) -> ToolResult:
        raw_path = call.arguments.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error="'path' must be a non-empty string",
            )
        candidate = (self.workspace_root / raw_path).resolve()
        if not self._is_inside_workspace(candidate):
            logger.warning("blocked file read outside workspace", extra={"tool_name": call.tool_name})
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error="path is outside the workspace",
            )
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error=str(exc),
            )
        logger.info(
            "builtin read_project_file completed",
            extra={"path": str(candidate.relative_to(self.workspace_root)), "content_length": len(content)},
        )
        return ToolResult(
            tool_name=call.tool_name,
            success=True,
            content=content,
            data={"path": str(candidate.relative_to(self.workspace_root))},
        )

    def _is_inside_workspace(self, path: Path) -> bool:
        return path == self.workspace_root or self.workspace_root in path.parents


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
