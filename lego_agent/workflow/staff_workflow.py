from __future__ import annotations

import logging

from lego_agent.core.models import (
    AssistantRequest,
    EventLevel,
    MemoryItem,
    Message,
    OutputContract,
    Project,
    ProjectResult,
    SkillSpec,
    Staff,
    StaffStatus,
    Task,
    TaskError,
    TaskExecutionResult,
    TaskStatus,
    ToolSpec,
    WorkContext,
    WorkResult,
)
from lego_agent.project.config import WorkflowConfig
from lego_agent.project.events import EventRecorder
from lego_agent.workflow.managers import (
    DefaultContextManager,
    NoopMemoryManager,
    NoopSkillManager,
    NoopToolManager,
)
from lego_agent.workflow.output import ProjectResultOutputParser, TaskExecutionResultOutputParser
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
        task_output_parser: TaskExecutionResultOutputParser | None = None,
        event_recorder: EventRecorder | None = None,
    ) -> None:
        self.context_manager = context_manager or DefaultContextManager()
        self.memory_manager = memory_manager or NoopMemoryManager()
        self.skill_manager = skill_manager or NoopSkillManager()
        self.tool_manager = tool_manager or NoopToolManager()
        self.prompt_builder = prompt_builder or DefaultPromptBuilder()
        self.output_parser = output_parser or ProjectResultOutputParser()
        self.task_output_parser = task_output_parser or TaskExecutionResultOutputParser()
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
            parsed_output = self.parse_output(response.content, project, staff, task)
            final_output = self._final_output(parsed_output)
            self.update_memory(project, staff, task, final_output)
            result = self.report_result(staff, task, final_output, parsed_output)
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
        output_contract = self._output_contract_for(staff)
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

    def _output_contract_for(self, staff: Staff) -> OutputContract:
        """Select the structured output contract for the current staff role."""
        if staff.role == "project_manager":
            return self._project_result_contract()
        return self._task_execution_result_contract()

    def _project_result_contract(self) -> OutputContract:
        """Build the schema contract expected from project manager output."""
        return OutputContract(
            name="ProjectResult",
            json_schema=ProjectResult.model_json_schema(),
            instructions=(
                "Produce the project manager's structured output. "
                "The staffing_plan must describe roles needed later; do not claim "
                "those staff have already executed work in Version 1."
            ),
        )

    def _task_execution_result_contract(self) -> OutputContract:
        """Build the schema contract expected from non-manager staff output."""
        return OutputContract(
            name="TaskExecutionResult",
            json_schema=TaskExecutionResult.model_json_schema(),
            instructions=(
                "Produce the assigned staff member's structured task output. "
                "Describe what you completed for this task only; do not create "
                "or modify the project staffing plan."
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

    def parse_output(
        self,
        content: str,
        project: Project,
        staff: Staff,
        task: Task,
    ) -> ProjectResult | TaskExecutionResult:
        """Turn assistant text into the structured contract for this staff."""
        self.hook_calls.append("parse_output")
        logger.debug(
            "workflow hook parse_output",
            extra={"project_id": project.id, "staff_id": staff.id, "task_id": task.id},
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Parsing assistant output.",
            actor_id=staff.id,
            task_id=task.id,
            data={"hook": "parse_output"},
        )
        if staff.role == "project_manager":
            return self.output_parser.parse(content, project)
        return self.task_output_parser.parse(content, project, task)

    def update_memory(self, project: Project, staff: Staff, task: Task, content: str) -> None:
        """Store useful output for future retrieval.

        The default memory manager ignores this call in Version 1.
        """
        self.hook_calls.append("update_memory")
        logger.debug(
            "workflow hook update_memory",
            extra={
                "project_id": project.id,
                "staff_id": staff.id,
                "task_id": task.id,
                "content_length": len(content),
            },
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Updating memory.",
            actor_id=staff.id,
            task_id=task.id,
            data={"hook": "update_memory"},
        )
        self.memory_manager.remember(
            project,
            staff,
            MemoryItem(scope="project", content=content, tags=[staff.role, "task_result"]),
        )

    def report_result(
        self,
        staff: Staff,
        task: Task,
        output: str,
        parsed_output: ProjectResult | TaskExecutionResult,
    ) -> WorkResult:
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
            project_result=parsed_output if isinstance(parsed_output, ProjectResult) else None,
            task_result=parsed_output if isinstance(parsed_output, TaskExecutionResult) else None,
        )

    def _final_output(self, parsed_output: ProjectResult | TaskExecutionResult) -> str:
        """Return the text stored on Task.result for either output contract."""
        return parsed_output.final_output


class IterativeStaffWorkflow(SinglePassStaffWorkflow):
    """Multi-round staff workflow with structured-output validation retries.

    This V2B-1 implementation does not execute real tool calls yet. Its job is
    to keep one task conversation alive when the assistant returns invalid
    structured output, append validation feedback, and retry within configured
    limits.
    """

    def __init__(
        self,
        workflow_config: WorkflowConfig | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.workflow_config = workflow_config or WorkflowConfig(type="iterative")

    def run(self, project: Project, staff: Staff, task: Task) -> WorkResult:
        """Run one staff task across multiple assistant steps when needed."""
        try:
            logger.info(
                "iterative staff workflow started",
                extra={
                    "project_id": project.id,
                    "staff_id": staff.id,
                    "task_id": task.id,
                    "max_steps": self.workflow_config.max_steps,
                    "max_output_retries": self.workflow_config.max_output_retries,
                },
            )
            self.event_recorder.project_event(
                project,
                "workflow_started",
                f"Iterative workflow started for task '{task.title}'.",
                actor_id=staff.id,
                task_id=task.id,
            )
            self.receive_task(staff, task)
            context = self.build_context(project, staff, task)
            memories = self.retrieve_memory(project, staff, task, context)
            skills = self.select_skills(project, staff, task, context)
            tools = self.select_tools(project, staff, task)
            request = self.plan_work(project, staff, task, context, skills, tools, memories)

            output_retry_count = 0
            last_error: Exception | None = None
            for step_number in range(1, self.workflow_config.max_steps + 1):
                self._record_step_started(project, staff, task, step_number)
                response = self.execute_work(staff, request)
                try:
                    parsed_output = self.parse_output_strict(response.content, project, staff, task)
                except Exception as exc:
                    last_error = exc
                    output_retry_count += 1
                    self._record_output_validation_failed(
                        project,
                        staff,
                        task,
                        step_number,
                        output_retry_count,
                        exc,
                    )
                    if output_retry_count > self.workflow_config.max_output_retries:
                        raise ValueError("assistant output remained invalid after retries") from exc
                    request.messages.append(self._validation_feedback_message(exc))
                    self._record_step_completed(project, staff, task, step_number, "retry")
                    continue

                final_output = self._final_output(parsed_output)
                self.update_memory(project, staff, task, final_output)
                result = self.report_result(staff, task, final_output, parsed_output)
                self._record_step_completed(project, staff, task, step_number, "done")
                self.event_recorder.project_event(
                    project,
                    "workflow_completed",
                    f"Iterative workflow completed for task '{task.title}'.",
                    actor_id=staff.id,
                    task_id=task.id,
                    data={"step_count": step_number, "output_retry_count": output_retry_count},
                )
                logger.info(
                    "iterative staff workflow completed",
                    extra={
                        "project_id": project.id,
                        "staff_id": staff.id,
                        "task_id": task.id,
                        "status": result.status.value,
                        "step_count": step_number,
                    },
                )
                return result

            self.event_recorder.project_event(
                project,
                "workflow_step_limit_reached",
                "Workflow reached max_steps before producing valid output.",
                level=EventLevel.ERROR,
                actor_id=staff.id,
                task_id=task.id,
                data={"max_steps": self.workflow_config.max_steps},
            )
            raise ValueError("workflow reached max_steps before producing valid output") from last_error
        except Exception as exc:
            return self._failed_work_result(project, staff, task, exc)

    def parse_output_strict(
        self,
        content: str,
        project: Project,
        staff: Staff,
        task: Task,
    ) -> ProjectResult | TaskExecutionResult:
        """Parse assistant output without fallback so invalid output can retry."""
        self.hook_calls.append("parse_output")
        logger.debug(
            "workflow hook parse_output_strict",
            extra={"project_id": project.id, "staff_id": staff.id, "task_id": task.id},
        )
        self.event_recorder.project_event(
            project,
            "workflow_hook",
            "Parsing assistant output strictly.",
            actor_id=staff.id,
            task_id=task.id,
            data={"hook": "parse_output_strict"},
        )
        if staff.role == "project_manager":
            return self.output_parser.parse_strict(content, project)
        return self.task_output_parser.parse_strict(content, project, task)

    def _validation_feedback_message(self, exc: Exception) -> Message:
        """Tell the assistant exactly why another structured response is needed."""
        return Message(
            role="user",
            content=(
                "The previous response did not match the required JSON output "
                f"contract. Error: {exc.__class__.__name__}: {exc}. "
                "Return exactly one valid JSON object that matches the requested "
                "output contract. Do not include Markdown fences or prose."
            ),
        )

    def _record_step_started(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        step_number: int,
    ) -> None:
        self.event_recorder.project_event(
            project,
            "workflow_step_started",
            f"Workflow step {step_number} started.",
            actor_id=staff.id,
            task_id=task.id,
            data={"step": step_number},
        )

    def _record_step_completed(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        step_number: int,
        outcome: str,
    ) -> None:
        self.event_recorder.project_event(
            project,
            "workflow_step_completed",
            f"Workflow step {step_number} completed with outcome '{outcome}'.",
            actor_id=staff.id,
            task_id=task.id,
            data={"step": step_number, "outcome": outcome},
        )

    def _record_output_validation_failed(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        step_number: int,
        retry_count: int,
        exc: Exception,
    ) -> None:
        self.event_recorder.project_event(
            project,
            "output_validation_failed",
            "Assistant output did not match the requested contract.",
            level=EventLevel.WARNING,
            actor_id=staff.id,
            task_id=task.id,
            data={
                "step": step_number,
                "retry_count": retry_count,
                "error_type": exc.__class__.__name__,
            },
        )

    def _failed_work_result(
        self,
        project: Project,
        staff: Staff,
        task: Task,
        exc: Exception,
    ) -> WorkResult:
        """Convert iterative workflow failures into task state and events."""
        logger.exception(
            "iterative staff workflow failed",
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
