from __future__ import annotations

import json
import logging
from typing import Any

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
                content=self._build_system_prompt(staff),
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

    def _build_system_prompt(self, staff: Staff) -> str:
        """Describe the staff member's stable role constraints.

        Responsibilities and capabilities belong in the system message because
        they define how this staff member should behave across tasks. The user
        message remains focused on the current project goal and task context.
        """
        responsibilities = self._format_named_items(
            [(item.name, item.description) for item in staff.responsibilities],
            empty_text="none",
        )
        capabilities = self._format_named_items(
            [(item.name, item.description) for item in staff.capabilities],
            empty_text="none",
        )
        description = staff.description or "No additional staff description."
        return (
            f"You are {staff.name}, {staff.title}.\n"
            f"Role: {staff.role}\n"
            f"Description: {description}\n\n"
            f"Responsibilities:\n{responsibilities}\n\n"
            f"Capabilities:\n{capabilities}\n\n"
            "Follow the unified StaffWorkflow. Stay within your responsibilities "
            "and use your capabilities to complete the assigned task. Return only "
            "one valid JSON object matching the requested project result contract. "
            "Do not wrap the JSON in Markdown. Do not include explanations before "
            "or after the JSON object."
        )

    def _format_named_items(self, items: list[tuple[str, str]], *, empty_text: str) -> str:
        """Format responsibility/capability lists for readable prompts."""
        if not items:
            return empty_text
        return "\n".join(f"- {name}: {description}" for name, description in items)

    def _format_output_contract(self, output_contract: OutputContract | None) -> str:
        if output_contract is None:
            logger.debug("using default project result output instructions")
            return (
                "Return JSON with keys: summary, project_understanding, "
                "assumptions, risks, staffing_plan, task_breakdown, "
                "execution_plan, final_output. staffing_plan must contain "
                "required_roles and rationale."
            )
        schema_json = json.dumps(
            self._compact_project_result_schema(output_contract.json_schema),
            indent=2,
            sort_keys=True,
        )
        logger.debug(
            "formatting output contract",
            extra={
                "output_contract": output_contract.name,
                "schema_chars": len(schema_json),
            },
        )
        return (
            f"Output contract: {output_contract.name}\n"
            f"{output_contract.instructions}\n\n"
            "Return exactly one JSON object. Do not use Markdown fences. "
            "Do not include comments or prose outside the JSON. "
            "Keep the output concise: use at most 3 assumptions, 3 risks, "
            "3 required roles, 5 task breakdown items, and 5 execution plan items. "
            "Keep each string under 120 characters where practical. "
            "Use this compact JSON shape:\n"
            f"{schema_json}"
        )

    def _compact_project_result_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Keep prompts short while preserving the output contract.

        The full Pydantic JSON schema remains available on
        `AssistantRequest.output_schema` for programmatic validation. The model
        prompt uses a smaller shape because some OpenAI-compatible providers can
        spend too long reasoning over verbose nested JSON Schema text.
        """
        if schema.get("title") != "ProjectResult":
            return schema
        return {
            "summary": "string",
            "project_understanding": "string",
            "assumptions": ["string"],
            "risks": ["string"],
            "staffing_plan": {
                "required_roles": [
                    {
                        "role": "string",
                        "title": "string",
                        "responsibilities": ["string"],
                        "capabilities": ["string"],
                        "task_focus": "string",
                        "priority": 1,
                    }
                ],
                "rationale": "string",
            },
            "task_breakdown": ["string"],
            "execution_plan": ["string"],
            "final_output": "string",
        }
