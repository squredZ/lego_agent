from __future__ import annotations

import logging

from lego_agent.core.models import (
    AssistantRequest,
    EventLevel,
    MemoryItem,
    OutputContract,
    Project,
    ProjectResult,
    SkillSpec,
    Staff,
    StaffStatus,
    Task,
    TaskError,
    TaskStatus,
    ToolSpec,
    WorkContext,
    WorkResult,
)
from lego_agent.project.events import EventRecorder
from lego_agent.workflow.managers import (
    DefaultContextManager,
    NoopMemoryManager,
    NoopSkillManager,
    NoopToolManager,
)
from lego_agent.workflow.output import ProjectResultOutputParser
from lego_agent.workflow.prompt import DefaultPromptBuilder

logger = logging.getLogger(__name__)


class SinglePassStaffWorkflow:
    """A simple implementation of the unified Staff workflow.

    "Single pass" means the assistant is called once. The hook methods are still
    split out so later versions can add real memory retrieval, tool calling,
    skill execution, retries, or multi-step planning without changing callers.
    """

    def __init__(
        self,
        context_manager: DefaultContextManager | None = None,
        memory_manager: NoopMemoryManager | None = None,
        skill_manager: NoopSkillManager | None = None,
        tool_manager: NoopToolManager | None = None,
        prompt_builder: DefaultPromptBuilder | None = None,
        output_parser: ProjectResultOutputParser | None = None,
        event_recorder: EventRecorder | None = None,
    ) -> None:
        self.context_manager = context_manager or DefaultContextManager()
        self.memory_manager = memory_manager or NoopMemoryManager()
        self.skill_manager = skill_manager or NoopSkillManager()
        self.tool_manager = tool_manager or NoopToolManager()
        self.prompt_builder = prompt_builder or DefaultPromptBuilder()
        self.output_parser = output_parser or ProjectResultOutputParser()
        self.event_recorder = event_recorder or EventRecorder()
        # Test/debug aid: records which workflow hooks ran and in what order.
        self.hook_calls: list[str] = []

    def run(self, project: Project, staff: Staff, task: Task) -> WorkResult:
        """Run all workflow hooks for one staff member and one task."""
        try:
            logger.info(
                "staff workflow started",
                extra={
                    "project_id": project.id,
                    "staff_id": staff.id,
                    "task_id": task.id,
                    "role": staff.role,
                },
            )
            self.event_recorder.project_event(
                project,
                "workflow_started",
                f"Workflow started for task '{task.title}'.",
                actor_id=staff.id,
                task_id=task.id,
            )
            self.receive_task(staff, task)
            context = self.build_context(project, staff, task)
            memories = self.retrieve_memory(project, staff, task, context)
            skills = self.select_skills(project, staff, task, context)
            tools = self.select_tools(project, staff, task)
            request = self.plan_work(project, staff, task, context, skills, tools, memories)
            response = self.execute_work(staff, request)
            project_result = self.parse_output(response.content, project)
            self.update_memory(project, staff, project_result.final_output)
            result = self.report_result(staff, task, project_result.final_output, project_result)
            self.event_recorder.project_event(
                project,
                "workflow_completed",
                f"Workflow completed for task '{task.title}'.",
                actor_id=staff.id,
                task_id=task.id,
            )
            logger.info(
                "staff workflow completed",
                extra={
                    "project_id": project.id,
                    "staff_id": staff.id,
                    "task_id": task.id,
                    "status": result.status.value,
                },
            )
            return result
        except Exception as exc:
            # Convert failures to WorkResult so orchestration can finish cleanly.
            logger.exception(
                "staff workflow failed",
                extra={
                    "project_id": project.id,
                    "staff_id": staff.id,
                    "task_id": task.id,
                    "error_type": exc.__class__.__name__,
                },
            )
            error = TaskError(type=exc.__class__.__name__, message=str(exc))
            task.status = TaskStatus.FAILED
            task.error = error
            staff.status = StaffStatus.IDLE
            staff.current_task_id = None
            self.event_recorder.project_event(
                project,
                "workflow_failed",
                str(exc),
                level=EventLevel.ERROR,
                actor_id=staff.id,
                task_id=task.id,
            )
            self.event_recorder.task_event(
                task,
                "task_failed",
                str(exc),
                level=EventLevel.ERROR,
                actor_id=staff.id,
            )
            return WorkResult(staff_id=staff.id, task_id=task.id, status=task.status, error=error)

    def receive_task(self, staff: Staff, task: Task) -> None:
        """Mark the task as assigned and the staff member as working."""
        self.hook_calls.append("receive_task")
        logger.debug(
            "workflow hook receive_task",
            extra={"project_id": task.project_id, "staff_id": staff.id, "task_id": task.id},
        )
        staff.assign(task)
        self.event_recorder.task_event(
            task,
            "task_received",
            f"Task assigned to staff '{staff.id}'.",
            actor_id=staff.id,
        )

    def build_context(self, project: Project, staff: Staff, task: Task) -> WorkContext:
        """Build the context package passed through the rest of the workflow."""
        self.hook_calls.append("build_context")
        logger.debug(
            "workflow hook build_context",
            extra={"project_id": project.id, "staff_id": staff.id, "task_id": task.id},
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Building work context.",
            actor_id=staff.id,
            task_id=task.id,
            data={"hook": "build_context"},
        )
        return self.context_manager.build_context(project, staff, task)

    def retrieve_memory(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        context: WorkContext,
    ) -> list[MemoryItem]:
        """Fetch relevant memory for this task.

        Version 1 uses a noop memory manager, but the hook is already in place
        so future persistent or vector memory can be plugged in here.
        """
        self.hook_calls.append("retrieve_memory")
        logger.debug(
            "workflow hook retrieve_memory",
            extra={"project_id": project.id, "staff_id": staff.id, "task_id": task.id},
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Retrieving memory.",
            actor_id=staff.id,
            task_id=task.id,
            data={"hook": "retrieve_memory"},
        )
        memories = self.memory_manager.retrieve(project, staff, task, task.goal)
        if memories:
            context.memory_context = "\n".join(item.content for item in memories)
        logger.debug(
            "memory retrieval completed",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "task_id": task.id,
                "memory_count": len(memories),
            },
        )
        return memories

    def select_skills(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        context: WorkContext,
    ) -> list[SkillSpec]:
        """Choose reusable work methods for the task."""
        self.hook_calls.append("select_skills")
        logger.debug(
            "workflow hook select_skills",
            extra={"project_id": project.id, "staff_id": staff.id, "task_id": task.id},
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Selecting skills.",
            actor_id=staff.id,
            task_id=task.id,
            data={"hook": "select_skills"},
        )
        skills = self.skill_manager.select_skills(staff, task, context)
        if skills:
            context.skill_context = "\n".join(item.instructions for item in skills)
        logger.debug(
            "skill selection completed",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "task_id": task.id,
                "skill_count": len(skills),
            },
        )
        return skills

    def select_tools(self, project: Project, staff: Staff, task: Task) -> list[ToolSpec]:
        """List tools available to the staff member for this task."""
        self.hook_calls.append("select_tools")
        logger.debug(
            "workflow hook select_tools",
            extra={"project_id": project.id, "staff_id": staff.id, "task_id": task.id},
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Selecting tools.",
            actor_id=staff.id,
            task_id=task.id,
            data={"hook": "select_tools"},
        )
        tools = self.tool_manager.list_tools(staff, task)
        logger.debug(
            "tool selection completed",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "task_id": task.id,
                "tool_count": len(tools),
            },
        )
        return tools

    def plan_work(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        context: WorkContext,
        skills: list[SkillSpec],
        tools: list[ToolSpec],
        memories: list[MemoryItem],
    ) -> AssistantRequest:
        """Create the assistant request from project, staff, task, and context."""
        self.hook_calls.append("plan_work")
        logger.debug(
            "workflow hook plan_work",
            extra={"project_id": project.id, "staff_id": staff.id, "task_id": task.id},
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Planning assistant request.",
            actor_id=staff.id,
            task_id=task.id,
            data={"hook": "plan_work"},
        )
        output_contract = self._project_result_contract()
        messages = self.prompt_builder.build_messages(
            project,
            staff,
            task,
            context,
            skills,
            tools,
            output_contract,
        )
        request = AssistantRequest(
            project=project,
            staff=staff,
            task=task,
            context=context,
            messages=messages,
            output_contract=output_contract,
            output_schema=output_contract.json_schema,
            metadata={"memory_count": len(memories)},
        )
        logger.debug(
            "assistant request planned",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "task_id": task.id,
                "message_count": len(messages),
                "output_contract": output_contract.name,
            },
        )
        return request

    def _project_result_contract(self) -> OutputContract:
        """Build the schema contract expected from the project manager output."""
        return OutputContract(
            name="ProjectResult",
            json_schema=ProjectResult.model_json_schema(),
            instructions=(
                "Produce the project manager's structured output. "
                "The staffing_plan must describe roles needed later; do not claim "
                "those staff have already executed work in Version 1."
            ),
        )

    def execute_work(self, staff: Staff, request: AssistantRequest):
        """Call the staff member's assistant."""
        self.hook_calls.append("execute_work")
        logger.debug(
            "workflow hook execute_work",
            extra={
                "project_id": request.project.id,
                "staff_id": staff.id,
                "task_id": request.task.id,
            },
        )
        self.event_recorder.project_event(
            request.project,
            "workflow_hook",
            "Executing assistant request.",
            actor_id=staff.id,
            task_id=request.task.id,
            data={"hook": "execute_work"},
        )
        if staff.assistant is None:
            raise ValueError(f"staff '{staff.id}' has no assistant")
        response = staff.assistant.respond(request)
        logger.debug(
            "assistant response received",
            extra={
                "project_id": request.project.id,
                "staff_id": staff.id,
                "task_id": request.task.id,
                "content_length": len(response.content),
                "has_structured": response.structured is not None,
            },
        )
        return response

    def parse_output(self, content: str, project: Project):
        """Turn assistant text into the structured project result contract."""
        self.hook_calls.append("parse_output")
        logger.debug(
            "workflow hook parse_output",
            extra={"project_id": project.id, "task_id": self._primary_task_id(project)},
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Parsing assistant output.",
            actor_id=project.manager_id,
            task_id=self._primary_task_id(project),
            data={"hook": "parse_output"},
        )
        return self.output_parser.parse(content, project)

    def update_memory(self, project: Project, staff: Staff, content: str) -> None:
        """Store useful output for future retrieval.

        The default memory manager ignores this call in Version 1.
        """
        self.hook_calls.append("update_memory")
        logger.debug(
            "workflow hook update_memory",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "task_id": self._primary_task_id(project),
                "content_length": len(content),
            },
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Updating memory.",
            actor_id=staff.id,
            task_id=self._primary_task_id(project),
            data={"hook": "update_memory"},
        )
        self.memory_manager.remember(
            project,
            staff,
            MemoryItem(scope="project", content=content, tags=["project_result"]),
        )

    def report_result(self, staff: Staff, task: Task, output: str, project_result) -> WorkResult:
        """Finalize task and staff status and return a workflow result."""
        self.hook_calls.append("report_result")
        logger.debug(
            "workflow hook report_result",
            extra={"project_id": task.project_id, "staff_id": staff.id, "task_id": task.id},
        )
        staff.complete(task, output)
        self.event_recorder.task_event(
            task,
            "task_completed",
            "Task completed successfully.",
            actor_id=staff.id,
        )
        return WorkResult(
            staff_id=staff.id,
            task_id=task.id,
            status=task.status,
            output=output,
            project_result=project_result,
        )

    def _primary_task_id(self, project: Project) -> str | None:
        """Return the only task id used by Version 1 PM-only orchestration."""
        if not project.tasks:
            return None
        return next(iter(project.tasks))
