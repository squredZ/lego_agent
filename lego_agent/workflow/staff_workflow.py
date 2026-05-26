from __future__ import annotations

from lego_agent.core.models import (
    AssistantRequest,
    MemoryItem,
    Project,
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
from lego_agent.workflow.managers import (
    DefaultContextManager,
    NoopMemoryManager,
    NoopSkillManager,
    NoopToolManager,
)
from lego_agent.workflow.output import ProjectResultOutputParser
from lego_agent.workflow.prompt import DefaultPromptBuilder


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
    ) -> None:
        self.context_manager = context_manager or DefaultContextManager()
        self.memory_manager = memory_manager or NoopMemoryManager()
        self.skill_manager = skill_manager or NoopSkillManager()
        self.tool_manager = tool_manager or NoopToolManager()
        self.prompt_builder = prompt_builder or DefaultPromptBuilder()
        self.output_parser = output_parser or ProjectResultOutputParser()
        # Test/debug aid: records which workflow hooks ran and in what order.
        self.hook_calls: list[str] = []

    def run(self, project: Project, staff: Staff, task: Task) -> WorkResult:
        """Run all workflow hooks for one staff member and one task."""
        try:
            self.receive_task(staff, task)
            context = self.build_context(project, staff, task)
            memories = self.retrieve_memory(project, staff, task, context)
            skills = self.select_skills(staff, task, context)
            tools = self.select_tools(staff, task)
            request = self.plan_work(project, staff, task, context, skills, tools, memories)
            response = self.execute_work(staff, request)
            project_result = self.parse_output(response.content, project)
            self.update_memory(project, staff, project_result.final_output)
            return self.report_result(staff, task, project_result.final_output, project_result)
        except Exception as exc:
            # Convert failures to WorkResult so orchestration can finish cleanly.
            error = TaskError(type=exc.__class__.__name__, message=str(exc))
            task.status = TaskStatus.FAILED
            task.error = error
            staff.status = StaffStatus.IDLE
            staff.current_task_id = None
            return WorkResult(staff_id=staff.id, task_id=task.id, status=task.status, error=error)

    def receive_task(self, staff: Staff, task: Task) -> None:
        """Mark the task as assigned and the staff member as working."""
        self.hook_calls.append("receive_task")
        staff.assign(task)

    def build_context(self, project: Project, staff: Staff, task: Task) -> WorkContext:
        """Build the context package passed through the rest of the workflow."""
        self.hook_calls.append("build_context")
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
        memories = self.memory_manager.retrieve(project, staff, task, task.goal)
        if memories:
            context.memory_context = "\n".join(item.content for item in memories)
        return memories

    def select_skills(
        self,
        staff: Staff,
        task: Task,
        context: WorkContext,
    ) -> list[SkillSpec]:
        """Choose reusable work methods for the task."""
        self.hook_calls.append("select_skills")
        skills = self.skill_manager.select_skills(staff, task, context)
        if skills:
            context.skill_context = "\n".join(item.instructions for item in skills)
        return skills

    def select_tools(self, staff: Staff, task: Task) -> list[ToolSpec]:
        """List tools available to the staff member for this task."""
        self.hook_calls.append("select_tools")
        return self.tool_manager.list_tools(staff, task)

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
        messages = self.prompt_builder.build_messages(project, staff, task, context, skills, tools)
        return AssistantRequest(
            project=project,
            staff=staff,
            task=task,
            context=context,
            messages=messages,
            metadata={"memory_count": len(memories)},
        )

    def execute_work(self, staff: Staff, request: AssistantRequest):
        """Call the staff member's assistant."""
        self.hook_calls.append("execute_work")
        if staff.assistant is None:
            raise ValueError(f"staff '{staff.id}' has no assistant")
        return staff.assistant.respond(request)

    def parse_output(self, content: str, project: Project):
        """Turn assistant text into the structured project result contract."""
        self.hook_calls.append("parse_output")
        return self.output_parser.parse(content, project)

    def update_memory(self, project: Project, staff: Staff, content: str) -> None:
        """Store useful output for future retrieval.

        The default memory manager ignores this call in Version 1.
        """
        self.hook_calls.append("update_memory")
        self.memory_manager.remember(
            project,
            staff,
            MemoryItem(scope="project", content=content, tags=["project_result"]),
        )

    def report_result(self, staff: Staff, task: Task, output: str, project_result) -> WorkResult:
        """Finalize task and staff status and return a workflow result."""
        self.hook_calls.append("report_result")
        staff.complete(task, output)
        return WorkResult(
            staff_id=staff.id,
            task_id=task.id,
            status=task.status,
            output=output,
            project_result=project_result,
        )
