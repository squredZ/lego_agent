from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from lego_agent.core.models import (
    AssistantRequest,
    AssistantResponse,
    ProjectResult,
    StaffRolePlan,
    StaffingPlan,
    TaskExecutionResult,
)

logger = logging.getLogger(__name__)


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
    response_format: dict[str, Any] | None = None
    stream: bool = False
    token_limit: int | None = None
    dry_run: bool | None = None

    def respond(self, request: AssistantRequest) -> AssistantResponse:
        """Return a model response or deterministic dry-run response."""
        if self._should_dry_run():
            logger.info(
                "assistant using dry-run response",
                extra={
                    "project_id": request.project.id,
                    "staff_id": request.staff.id,
                    "task_id": request.task.id,
                    "model": self.model,
                },
            )
            return self._dry_run_response(request)

        from openai import OpenAI

        client_kwargs: dict[str, Any] = {}
        api_key = self._effective_api_key()
        base_url = self._effective_base_url()
        logger.info(
            "assistant calling OpenAI-compatible API",
            extra={
                "project_id": request.project.id,
                "staff_id": request.staff.id,
                "task_id": request.task.id,
                "model": self.model,
                "has_api_key": bool(api_key),
                "has_base_url": bool(base_url),
                "timeout_seconds": self.timeout_seconds,
                "stream": self.stream,
            },
        )
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        if self.timeout_seconds is not None:
            client_kwargs["timeout"] = self.timeout_seconds

        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(**self._chat_completion_kwargs(request))
        content = (
            self._streaming_chat_completion_content(response)
            if self.stream
            else self._chat_completion_content(response)
        )
        logger.info(
            "assistant received OpenAI-compatible response",
            extra={
                "project_id": request.project.id,
                "staff_id": request.staff.id,
                "task_id": request.task.id,
                "model": self.model,
                "content_length": len(content),
            },
        )
        return AssistantResponse(content=content, raw=response)

    def _chat_completion_kwargs(self, request: AssistantRequest) -> dict[str, Any]:
        """Map framework request fields to Chat Completions parameters."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._chat_messages(request),
            "stream": self.stream,
        }
        if self.token_limit is not None:
            # Chat Completions-compatible providers commonly use `max_tokens`.
            # Keep `token_limit` as the framework-level name so callers do not
            # depend on provider-specific parameter names.
            kwargs["max_tokens"] = self.token_limit
        if self.reasoning_effort and self._thinking_enabled():
            kwargs["reasoning_effort"] = self.reasoning_effort
        if self.response_format:
            kwargs["response_format"] = self.response_format
        if self.thinking:
            kwargs["extra_body"] = {"thinking": self.thinking}
        logger.debug(
            "built OpenAI-compatible chat completion kwargs",
            extra={
                "model": self.model,
                "has_token_limit": self.token_limit is not None,
                "has_reasoning_effort": bool(self.reasoning_effort and self._thinking_enabled()),
                "has_response_format": bool(self.response_format),
                "has_thinking": bool(self.thinking),
                "stream": self.stream,
                "message_count": len(kwargs["messages"]),
            },
        )
        return kwargs

    def _thinking_enabled(self) -> bool:
        """Return whether DeepSeek/OpenAI-compatible thinking mode is enabled.

        DeepSeek V4 enables thinking by default. If config explicitly disables
        it, reasoning effort should not be sent because there is no reasoning
        budget to control.
        """
        if self.thinking is None:
            return True
        return self.thinking.get("type") != "disabled"

    def _chat_messages(self, request: AssistantRequest) -> list[dict[str, str]]:
        """Return Chat Completions messages while preserving workflow prompts."""
        if request.messages:
            return [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ]
        return [
            {"role": "system", "content": self._system_prompt(request)},
            {"role": "user", "content": self._user_prompt(request)},
        ]

    def _chat_completion_content(self, response: Any) -> str:
        """Extract assistant text from a Chat Completions response."""
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise ValueError("chat completion response did not contain assistant content") from exc
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return self._content_parts_to_text(content)
        if content is None:
            return ""
        return str(content)

    def _streaming_chat_completion_content(self, stream: Any) -> str:
        """Collect text from a Chat Completions streaming response.

        The framework still returns one `AssistantResponse` in Version 1. This
        method lets provider streaming be enabled without changing workflow
        contracts; future CLI/API streaming can expose chunks directly.
        """
        text_parts: list[str] = []
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta
            except (AttributeError, IndexError):
                continue
            content = getattr(delta, "content", None)
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                text_parts.append(self._content_parts_to_text(content))
        return "".join(text_parts)

    def _content_parts_to_text(self, parts: list[Any]) -> str:
        """Handle providers that return message content as typed parts."""
        text_parts: list[str] = []
        for part in parts:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
            else:
                text = getattr(part, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts)

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
        """Build a valid structured response without calling a remote model.

        Dry-run keeps local tests and examples deterministic. It also documents
        the structured output each built-in workflow contract should produce.
        """
        if request.output_contract and request.output_contract.name == "TaskExecutionResult":
            return self._dry_run_task_execution_response(request)
        return self._dry_run_project_result_response(request)

    def _dry_run_project_result_response(self, request: AssistantRequest) -> AssistantResponse:
        """Build a valid ProjectResult for project manager planning."""
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
        logger.debug(
            "assistant dry-run response built",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "task_id": task.id,
                "model": self.model,
            },
        )
        return AssistantResponse(
            content=project_result.model_dump_json(),
            structured=project_result.model_dump(mode="json"),
        )

    def _dry_run_task_execution_response(self, request: AssistantRequest) -> AssistantResponse:
        """Build a valid TaskExecutionResult for recruited staff tasks."""
        task_result = TaskExecutionResult(
            summary=f"{request.staff.name} completed the assigned task.",
            work_performed=[f"Handled task goal: {request.task.goal}"],
            deliverables=[f"Draft deliverable for {request.task.title}"],
            blockers=[],
            next_steps=["Wait for project manager review."],
            final_output=f"[dry-run:{self.model}] {request.staff.role} handled '{request.task.goal}'.",
        )
        logger.debug(
            "assistant dry-run task response built",
            extra={
                "project_id": request.project.id,
                "staff_id": request.staff.id,
                "task_id": request.task.id,
                "model": self.model,
            },
        )
        return AssistantResponse(
            content=task_result.model_dump_json(),
            structured=task_result.model_dump(mode="json"),
        )
