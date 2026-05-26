from __future__ import annotations

from lego_agent.core.models import Message, Project, SkillSpec, Staff, Task, ToolSpec, WorkContext


class DefaultPromptBuilder:
    """Builds assistant messages for the single-pass workflow.

    Prompt construction is isolated here so the workflow stays focused on
    orchestration. Later roles can swap this builder without changing runtime
    code.
    """

    def build_messages(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        context: WorkContext,
        skills: list[SkillSpec],
        tools: list[ToolSpec],
    ) -> list[Message]:
        skill_text = "\n".join(f"- {item.name}: {item.instructions}" for item in skills)
        tool_text = "\n".join(f"- {item.name}: {item.description}" for item in tools)
        return [
            Message(
                role="system",
                content=(
                    f"You are {staff.name}, {staff.title}. "
                    "Follow the unified StaffWorkflow and return only valid JSON "
                    "matching the requested project result contract."
                ),
            ),
            Message(
                role="user",
                content=(
                    f"Project goal:\n{project.goal}\n\n"
                    f"Task:\n{task.goal}\n\n"
                    f"Role context:\n{context.role_context or ''}\n\n"
                    f"Memory context:\n{context.memory_context or 'none'}\n\n"
                    f"Selected skills:\n{skill_text or 'none'}\n\n"
                    f"Available tools:\n{tool_text or 'none'}\n\n"
                    "Return JSON with keys: summary, project_understanding, "
                    "assumptions, risks, staffing_plan, task_breakdown, "
                    "execution_plan, final_output. staffing_plan must contain "
                    "required_roles and rationale."
                ),
            ),
        ]
