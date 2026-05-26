from __future__ import annotations

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


class DefaultContextManager:
    """Builds the minimal context needed by Version 1.

    Context is intentionally a separate object instead of being stored on Staff.
    Each task run can build different context from the same project and staff.
    """

    def build_context(self, project: Project, staff: Staff, task: Task) -> WorkContext:
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
        return []

    def remember(self, project: Project, staff: Staff, item: MemoryItem) -> None:
        return None


class NoopToolManager:
    """Tool interface placeholder.

    Version 1 can describe where tools will fit, but assistant-requested tool
    execution is intentionally disabled.
    """

    def list_tools(self, staff: Staff, task: Task) -> list[ToolSpec]:
        return []

    def call_tool(self, call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_name=call.tool_name,
            success=False,
            error="tool execution is not enabled in version 1",
        )


class NoopSkillManager:
    """Skill interface placeholder.

    Skills are reusable work methods. Version 1 does not execute nested skill
    runtimes, so this manager returns no selected skills.
    """

    def list_skills(self, staff: Staff, task: Task) -> list[SkillSpec]:
        return []

    def select_skills(
        self,
        staff: Staff,
        task: Task,
        context: WorkContext,
    ) -> list[SkillSpec]:
        return []
