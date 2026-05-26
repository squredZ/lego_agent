from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from lego_agent.core.models import (
    AssistantRequest,
    AssistantResponse,
    ProjectResult,
    StaffRolePlan,
    StaffingPlan,
)


@dataclass(slots=True)
class OpenAIAssistant:
    """OpenAI-compatible assistant adapter.

    The rest of the framework talks to `AssistantRequest` and
    `AssistantResponse`. This adapter is the only place that knows the OpenAI
    SDK request shape, which keeps workflows provider-agnostic.
    """

    model: str = "gpt-4.1-mini"
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: float | None = None
    thinking: dict[str, Any] | None = None
    reasoning_effort: str | None = None
    token_limit: int | None = None
    dry_run: bool | None = None

    def respond(self, request: AssistantRequest) -> AssistantResponse:
        """Return a model response or deterministic dry-run response."""
        if self._should_dry_run():
            return self._dry_run_response(request)

        from openai import OpenAI

        client_kwargs: dict[str, Any] = {}
        api_key = self._effective_api_key()
        base_url = self._effective_base_url()
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        if self.timeout_seconds is not None:
            client_kwargs["timeout"] = self.timeout_seconds

        client = OpenAI(**client_kwargs)
        response = client.responses.create(**self._response_kwargs(request))
        return AssistantResponse(content=response.output_text, raw=response)

    def _response_kwargs(self, request: AssistantRequest) -> dict[str, Any]:
        """Map framework request fields to OpenAI Responses API parameters."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": self._system_prompt(request),
                },
                {
                    "role": "user",
                    "content": self._user_prompt(request),
                },
            ],
        }
        if self.token_limit is not None:
            kwargs["max_output_tokens"] = self.token_limit
        if self.reasoning_effort:
            kwargs["reasoning"] = {"effort": self.reasoning_effort}
        if self.thinking:
            kwargs["extra_body"] = {"thinking": self.thinking}
        return kwargs

    def _should_dry_run(self) -> bool:
        """Use dry-run unless explicitly disabled and an API key is available."""
        if self.dry_run is not None:
            return self.dry_run
        return not self._effective_api_key()

    def _effective_api_key(self) -> str | None:
        return self.api_key or os.environ.get("OPENAI_API_KEY")

    def _effective_base_url(self) -> str | None:
        return self.base_url or os.environ.get("OPENAI_BASE_URL")

    def _system_prompt(self, request: AssistantRequest) -> str:
        staff = request.staff
        responsibilities = "; ".join(
            item.description for item in staff.responsibilities
        ) or "General execution."
        capabilities = ", ".join(item.name for item in staff.capabilities) or "none"
        return (
            f"You are {staff.name}, {staff.title}. "
            f"Responsibilities: {responsibilities}. "
            f"Capabilities: {capabilities}. "
            "Return concise, actionable work output."
        )

    def _user_prompt(self, request: AssistantRequest) -> str:
        if request.messages:
            return "\n\n".join(message.content for message in request.messages)
        return (
            f"Project goal: {request.project.goal}\n"
            f"Task: {request.task.goal}\n"
            f"Context: {request.context.model_dump_json()}"
        )

    def _dry_run_response(self, request: AssistantRequest) -> AssistantResponse:
        """Build a valid ProjectResult without calling a remote model.

        Dry-run keeps local tests and examples deterministic. It also documents
        the structured output the real project manager prompt should produce.
        """
        staff = request.staff
        project = request.project
        task = request.task
        role_plan = StaffRolePlan(
            role="implementation_staff",
            title="Implementation Staff",
            responsibilities=["implementation"],
            capabilities=["execution_planning"],
            task_focus="Implement the project deliverables after project planning.",
            priority=1,
        )
        staffing_plan = StaffingPlan(
            required_roles=[role_plan],
            rationale="A project manager should recruit implementation and review support once planning is approved.",
        )
        project_result = ProjectResult(
            summary=f"{staff.name} prepared an initial project plan.",
            project_understanding=f"The project goal is: {project.goal}",
            assumptions=["Requirements may need refinement during execution."],
            risks=["Scope may expand if acceptance criteria are not clarified."],
            staffing_plan=staffing_plan,
            task_breakdown=[
                "Clarify success criteria.",
                "Recruit required project roles.",
                "Execute implementation tasks.",
                "Review and accept final output.",
            ],
            execution_plan=[
                "Confirm project goal and constraints.",
                "Use the staffing plan to assemble project staff in a later phase.",
                "Track task completion and review deliverables.",
            ],
            final_output=f"[dry-run:{self.model}] Project manager handled '{task.goal}'.",
        )
        return AssistantResponse(
            content=project_result.model_dump_json(),
            structured=project_result.model_dump(mode="json"),
        )
