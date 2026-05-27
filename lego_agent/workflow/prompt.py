from __future__ import annotations

import json
import logging

from lego_agent.core.models import (
    Message,
    OutputContract,
    Project,
    SkillSpec,
    Staff,
    Task,
    ToolSpec,
    WorkContext,
)

logger = logging.getLogger(__name__)


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
        output_contract: OutputContract | None = None,
    ) -> list[Message]:
        logger.debug(
            "building assistant messages",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "task_id": task.id,
                "skill_count": len(skills),
                "tool_count": len(tools),
                "has_output_contract": output_contract is not None,
            },
        )
        skill_text = "\n".join(f"- {item.name}: {item.instructions}" for item in skills)
        tool_text = "\n".join(f"- {item.name}: {item.description}" for item in tools)
        contract_text = self._format_output_contract(output_contract)
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
                    f"{contract_text}"
                ),
            ),
        ]

    def _format_output_contract(self, output_contract: OutputContract | None) -> str:
        if output_contract is None:
            logger.debug("using default project result output instructions")
            return (
                "Return JSON with keys: summary, project_understanding, "
                "assumptions, risks, staffing_plan, task_breakdown, "
                "execution_plan, final_output. staffing_plan must contain "
                "required_roles and rationale."
            )
        schema_json = json.dumps(output_contract.json_schema, indent=2, sort_keys=True)
        logger.debug(
            "formatting output contract",
            extra={
                "output_contract": output_contract.name,
                "schema_key_count": len(output_contract.json_schema),
            },
        )
        return (
            f"Output contract: {output_contract.name}\n"
            f"{output_contract.instructions}\n\n"
            "Return only valid JSON matching this JSON schema:\n"
            f"{schema_json}"
        )
