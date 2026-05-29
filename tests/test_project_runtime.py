from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from lego_agent.assistants.openai_assistant import OpenAIAssistant
from lego_agent.cli import main
from lego_agent.core.models import (
    AssistantRequest,
    AssistantResponse,
    Message,
    Project,
    ProjectStatus,
    Staff,
    StaffInbox,
    StaffMessage,
    StaffRolePlan,
    StaffingPlan,
    Task,
    TaskExecutionResult,
    TaskStatus,
    ToolCall,
    WorkResult,
    WorkContext,
)
from lego_agent.project.config import parse_project_runtime_config
from lego_agent.project.events import EventRecorder
from lego_agent.project.interaction import (
    InMemoryMessageBus,
    InMemoryTaskStore,
    TaskCompletionHandler,
    TaskDispatcher,
)
from lego_agent.project.runtime import create_project_runtime
from lego_agent.project.staffing import StaffFactory, StaffProfileResolver, normalize_staff_role_id
from lego_agent.workflow.managers import BuiltinToolManager, NoopMemoryManager, NoopSkillManager, NoopToolManager
from lego_agent.workflow.output import ProjectResultOutputParser
from lego_agent.workflow.staff_workflow import IterativeStaffWorkflow, SinglePassStaffWorkflow


@pytest.fixture(autouse=True)
def _isolate_llm_environment(monkeypatch) -> None:
    """Keep unit tests deterministic even when the developer has real keys set."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


def _config() -> dict[str, object]:
    return {
        "project": {"default_manager_profile": "project_manager"},
        "orchestration": {"strategy": "project_manager_only"},
        "staff_profiles": {
            "project_manager": {
                "name": "Ava",
                "role": "project_manager",
                "title": "Project Manager",
                "responsibilities": ["requirements_analysis", "planning", "staffing"],
                "capabilities": ["task_decomposition", "staff_recruitment"],
                "assistant": {
                    "type": "openai",
                    "model": "test-model",
                    "dry_run": True,
                    "token_limit": 2048,
                },
            }
        },
    }


def _config_with_staff_profiles() -> dict[str, object]:
    config = _config()
    config["staff_profiles"]["implementation_staff"] = {
        "name": "Iris",
        "role": "implementation_staff",
        "title": "Implementation Staff",
        "responsibilities": ["implementation"],
        "capabilities": ["code_generation", "execution_planning"],
        "assistant": {
            "type": "openai",
            "model": "test-model",
            "dry_run": True,
        },
    }
    return config


def _assistant_request(project: Project, staff: Staff) -> AssistantRequest:
    task = Task(project_id=project.id, title="Plan", goal="Plan")
    context = WorkContext(
        project_id=project.id,
        task_id=task.id,
        staff_id=staff.id,
        project_goal=project.goal,
        task_goal=task.goal,
    )
    return AssistantRequest(project=project, staff=staff, task=task, context=context)


def _manager_task(project: Project) -> Task:
    return next(iter(project.tasks.values()))


def _project_with_worker() -> tuple[Project, Staff, Staff]:
    manager = Staff(
        id="project_manager",
        project_id="project",
        name="Ava",
        role="project_manager",
        title="Project Manager",
    )
    worker = Staff(
        id="implementation_staff",
        project_id="project",
        name="Iris",
        role="implementation_staff",
        title="Implementation Staff",
        manager_id=manager.id,
    )
    project = Project(
        id="project",
        goal="Build",
        manager_id=manager.id,
        staff={manager.id: manager, worker.id: worker},
    )
    return project, manager, worker


def test_project_model_requires_project_manager_role() -> None:
    manager = Staff(
        id="pm",
        project_id="project",
        name="Ava",
        role="engineer",
        title="Engineer",
    )

    try:
        Project(goal="Build", manager_id="pm", staff={"pm": manager})
    except ValueError as exc:
        assert "project_manager" in str(exc)
    else:
        raise AssertionError("expected invalid manager role to fail")


def test_staff_inbox_exposes_unread_messages() -> None:
    read_message = StaffMessage(
        project_id="project",
        sender_id="manager",
        recipient_id="worker",
        type="task_assigned",
        content="Read message.",
    )
    read_message.read_at = read_message.created_at
    unread_message = StaffMessage(
        project_id="project",
        sender_id="manager",
        recipient_id="worker",
        type="task_assigned",
        content="Unread message.",
    )

    inbox = StaffInbox(
        staff_id="worker",
        project_id="project",
        messages=[read_message, unread_message],
    )

    assert inbox.unread == [unread_message]


def test_in_memory_message_bus_tracks_unread_messages() -> None:
    bus = InMemoryMessageBus()
    message = bus.send(
        StaffMessage(
            project_id="project",
            sender_id="manager",
            recipient_id="worker",
            type="task_assigned",
            content="Please handle this task.",
        )
    )

    assert bus.unread_for("worker", "project") == [message]

    bus.mark_read(message.id)

    assert bus.unread_for("worker", "project") == []


def test_task_dispatcher_assigns_task_and_notifies_worker() -> None:
    project, manager, worker = _project_with_worker()
    task_store = InMemoryTaskStore(project)
    message_bus = InMemoryMessageBus()
    event_recorder = EventRecorder()
    dispatcher = TaskDispatcher(task_store, message_bus, event_recorder)
    child_task = Task(
        project_id=project.id,
        title="Implement core runtime",
        goal="Implement core runtime",
        parent_task_id="manager-task",
    )

    dispatcher.assign(project, child_task, worker, manager)

    assert project.tasks[child_task.id].assigned_to == worker.id
    assert project.tasks[child_task.id].created_by == manager.id
    assert message_bus.unread_for(worker.id, project.id)[0].type == "task_assigned"
    assert any(event.type == "task_assigned" for event in project.events)
    assert any(event.type == "task_assigned" for event in child_task.events)


def test_task_completion_handler_notifies_manager() -> None:
    project, manager, worker = _project_with_worker()
    child_task = Task(
        project_id=project.id,
        title="Implement core runtime",
        goal="Implement core runtime",
        assigned_to=worker.id,
        created_by=manager.id,
        parent_task_id="manager-task",
    )
    project.tasks[child_task.id] = child_task
    task_store = InMemoryTaskStore(project)
    message_bus = InMemoryMessageBus()
    event_recorder = EventRecorder()
    completion_handler = TaskCompletionHandler(task_store, message_bus, event_recorder)
    work_result = WorkResult(
        staff_id=worker.id,
        task_id=child_task.id,
        status=TaskStatus.DONE,
        output="Implemented core runtime.",
    )

    completion_handler.complete(project, child_task, worker, work_result)

    assert project.tasks[child_task.id].status == TaskStatus.DONE
    assert project.tasks[child_task.id].result == "Implemented core runtime."
    manager_messages = message_bus.unread_for(manager.id, project.id)
    assert manager_messages[0].type == "task_completed"
    assert manager_messages[0].sender_id == worker.id
    assert any(event.type == "task_completed" for event in project.events)
    assert any(event.type == "task_completed" for event in child_task.events)


def test_parses_project_runtime_config() -> None:
    config = parse_project_runtime_config(_config())

    assert config.project.default_manager_profile == "project_manager"
    assert config.orchestration.strategy == "project_manager_only"
    assert config.workflow.type == "single_pass"
    assert config.staff_profiles["project_manager"].assistant.token_limit == 2048


def test_parses_iterative_workflow_config() -> None:
    raw_config = _config()
    raw_config["workflow"] = {
        "type": "iterative",
        "max_steps": 4,
        "max_output_retries": 1,
    }

    config = parse_project_runtime_config(raw_config)

    assert config.workflow.type == "iterative"
    assert config.workflow.max_steps == 4
    assert config.workflow.max_output_retries == 1


def test_parses_builtin_tool_config() -> None:
    raw_config = _config()
    raw_config["workflow"] = {
        "type": "iterative",
        "tools": "builtin",
        "enabled_tools": ["echo"],
        "workspace_root": "/tmp",
    }

    config = parse_project_runtime_config(raw_config)

    assert config.workflow.tools == "builtin"
    assert config.workflow.enabled_tools == ["echo"]
    assert config.workflow.workspace_root == "/tmp"


def test_rejects_invalid_workflow_limits() -> None:
    raw_config = _config()
    raw_config["workflow"] = {"type": "iterative", "max_steps": 0}

    with pytest.raises(ValueError):
        parse_project_runtime_config(raw_config)


def test_project_manager_only_dry_run_returns_project_result() -> None:
    runtime = create_project_runtime(parse_project_runtime_config(_config()))

    result = runtime.run("Build a project-oriented agent framework")

    assert result.status == ProjectStatus.DONE
    assert result.manager_id == "project_manager"
    assert result.result is not None
    assert result.result.staffing_plan.required_roles
    assert "Build a project-oriented agent framework" in result.result.project_understanding


def test_runtime_creates_iterative_workflow_from_config() -> None:
    raw_config = _config()
    raw_config["workflow"] = {"type": "iterative", "max_steps": 3}

    runtime = create_project_runtime(parse_project_runtime_config(raw_config))

    assert isinstance(runtime.workflow, IterativeStaffWorkflow)
    assert runtime.workflow.workflow_config.max_steps == 3


def test_runtime_injects_builtin_tool_manager_from_config() -> None:
    raw_config = _config()
    raw_config["workflow"] = {"type": "iterative", "tools": "builtin", "enabled_tools": ["echo"]}

    runtime = create_project_runtime(parse_project_runtime_config(raw_config))

    assert isinstance(runtime.workflow.tool_manager, BuiltinToolManager)


def test_project_run_records_events() -> None:
    runtime = create_project_runtime(parse_project_runtime_config(_config()))

    result = runtime.run("Build a project-oriented agent framework")

    event_types = [event.type for event in result.events]
    assert "project_created" in event_types
    assert "manager_created" in event_types
    assert "task_created" in event_types
    assert "workflow_started" in event_types
    assert "project_completed" in event_types
    assert any(event.type == "workflow_hook" for event in result.events)


def test_project_run_attaches_staff_profile_resolution() -> None:
    runtime = create_project_runtime(parse_project_runtime_config(_config_with_staff_profiles()))

    result = runtime.run("Build a project-oriented agent framework")

    assert result.staffing_profile_resolution is not None
    match = result.staffing_profile_resolution.matches[0]
    assert match.matched is True
    assert match.planned_role == "implementation_staff"
    assert match.profile_name == "implementation_staff"
    assert match.source == "profile"


def test_project_manager_with_staff_creates_recruited_staff_and_child_tasks() -> None:
    raw_config = _config_with_staff_profiles()
    raw_config["orchestration"] = {"strategy": "project_manager_with_staff"}
    runtime = create_project_runtime(parse_project_runtime_config(raw_config))
    project = runtime.create_project("Build a project-oriented agent framework")

    result = runtime.orchestrator.run(project)

    assert result.status == ProjectStatus.REVIEWING
    assert result.completed_at is not None
    assert project.completed_at is None
    assert "implementation_staff" in project.staff
    assert project.staff["implementation_staff"].manager_id == "project_manager"
    child_tasks = [
        task
        for task in project.tasks.values()
        if task.parent_task_id == _manager_task(project).id
    ]
    assert len(child_tasks) == 1
    assert child_tasks[0].assigned_to == "implementation_staff"
    assert child_tasks[0].status == TaskStatus.DONE
    assert child_tasks[0].result is not None
    assert "implementation_staff handled" in child_tasks[0].result
    event_types = [event.type for event in result.events]
    assert "staff_created" in event_types
    assert "task_assigned" in event_types
    assert "project_staffing_completed" in event_types
    assert "child_task_execution_started" in event_types
    assert "project_ready_for_review" in event_types


def test_staff_profile_resolver_marks_unknown_roles_as_dynamic() -> None:
    config = parse_project_runtime_config(_config())
    staffing_plan = StaffingPlan(
        required_roles=[
            StaffRolePlan(
                role="security_staff",
                title="Security Staff",
                responsibilities=["review"],
                capabilities=["quality_review"],
                task_focus="Review security risks.",
            )
        ],
        rationale="Security review is required.",
    )

    resolution = StaffProfileResolver(config.staff_profiles, config.dynamic_staff).resolve(staffing_plan)

    assert resolution.unresolved == []
    assert resolution.matches[0].matched is True
    assert resolution.matches[0].source == "dynamic"
    assert "created dynamically" in resolution.matches[0].reason


def test_staff_factory_creates_dynamic_staff_from_role_plan() -> None:
    config = parse_project_runtime_config(_config())
    role_plan = StaffRolePlan(
        role="security_staff",
        title="Security Staff",
        responsibilities=["security_review"],
        capabilities=["threat_modeling"],
        task_focus="Review security risks.",
    )
    factory = StaffFactory(
        config.staff_profiles,
        config.dynamic_staff,
        lambda assistant_config: OpenAIAssistant(**assistant_config.to_assistant_kwargs()),
    )

    staff = factory.create_from_plan(role_plan, "project", manager_id="project_manager")

    assert staff.id == "security_staff"
    assert staff.role == "security_staff"
    assert staff.title == "Security Staff"
    assert staff.manager_id == "project_manager"
    assert staff.responsibilities[0].name == "security_review"
    assert staff.capabilities[0].name == "threat_modeling"
    assert isinstance(staff.assistant, OpenAIAssistant)


def test_dynamic_staff_role_ids_are_normalized_for_runtime_state() -> None:
    config = parse_project_runtime_config(_config())
    role_plan = StaffRolePlan(
        role="Frontend Developer",
        title="Frontend Developer",
        responsibilities=["implementation"],
        capabilities=["execution_planning"],
        task_focus="Build the minimal UI.",
    )
    factory = StaffFactory(
        config.staff_profiles,
        config.dynamic_staff,
        lambda assistant_config: OpenAIAssistant(**assistant_config.to_assistant_kwargs()),
    )

    staff = factory.create_from_plan(role_plan, "project", manager_id="project_manager")

    assert normalize_staff_role_id("Frontend Developer") == "frontend_developer"
    assert staff.id == "frontend_developer"
    assert staff.role == "frontend_developer"
    assert staff.title == "Frontend Developer"
    assert staff.metadata["planned_role"] == "Frontend Developer"


def test_staff_profile_resolver_matches_normalized_role_to_profile() -> None:
    config = parse_project_runtime_config(_config_with_staff_profiles())
    staffing_plan = StaffingPlan(
        required_roles=[
            StaffRolePlan(
                role="Implementation Staff",
                title="Implementation Staff",
                responsibilities=["implementation"],
                capabilities=["execution_planning"],
                task_focus="Implement the project.",
            )
        ],
        rationale="Implementation is required.",
    )

    resolution = StaffProfileResolver(config.staff_profiles, config.dynamic_staff).resolve(staffing_plan)

    assert resolution.matches[0].matched is True
    assert resolution.matches[0].source == "profile"
    assert resolution.matches[0].profile_name == "implementation_staff"


def test_project_run_emits_useful_logs(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    runtime = create_project_runtime(parse_project_runtime_config(_config()))

    result = runtime.run("Build a project-oriented agent framework")

    assert result.status == ProjectStatus.DONE
    messages = [record.getMessage() for record in caplog.records]
    assert "project run started" in messages
    assert "staff workflow started" in messages
    assert "assistant using dry-run response" in messages
    assert "project manager orchestration completed" in messages
    assert all("test-key" not in record.getMessage() for record in caplog.records)


def test_workflow_exposes_expected_hook_order() -> None:
    workflow = SinglePassStaffWorkflow()
    runtime = create_project_runtime(parse_project_runtime_config(_config()))
    runtime.workflow = workflow
    runtime.orchestrator.workflow = workflow

    result = runtime.run("Plan the project")

    assert result.status == ProjectStatus.DONE
    assert workflow.hook_calls == [
        "receive_task",
        "build_context",
        "retrieve_memory",
        "select_skills",
        "select_tools",
        "plan_work",
        "execute_work",
        "parse_output",
        "update_memory",
        "report_result",
    ]


def test_workflow_adds_project_result_output_contract() -> None:
    captured = {}

    class CapturingAssistant:
        """Test fake that records the request before delegating to dry-run output."""

        def respond(self, request):
            captured["request"] = request
            return OpenAIAssistant(model="test-model", dry_run=True).respond(request)

    runtime = create_project_runtime(parse_project_runtime_config(_config()))
    project = runtime.create_project("Plan the project")
    project.manager.assistant = CapturingAssistant()
    task = _manager_task(project)

    result = runtime.workflow.run(project, project.manager, task)
    request = captured["request"]

    assert result.status == TaskStatus.DONE
    assert request.output_contract.name == "ProjectResult"
    assert request.output_schema["title"] == "ProjectResult"
    system_prompt = request.messages[0].content
    user_prompt = request.messages[-1].content
    assert "You are Ava, Project Manager." in system_prompt
    assert "Role: project_manager" in system_prompt
    assert "Responsibilities:" in system_prompt
    assert "requirements_analysis" in system_prompt
    assert "planning" in system_prompt
    assert "staffing" in system_prompt
    assert "Capabilities:" in system_prompt
    assert "task_decomposition" in system_prompt
    assert "staff_recruitment" in system_prompt
    assert "ProjectResult" in user_prompt
    assert "Return exactly one JSON object" in user_prompt
    assert "Do not use Markdown fences" in user_prompt
    assert "at most 3 assumptions" in user_prompt


def test_workflow_adds_task_execution_output_contract_for_worker() -> None:
    captured = {}

    class CapturingAssistant:
        """Test fake that records the worker request."""

        def respond(self, request):
            captured["request"] = request
            return OpenAIAssistant(model="test-model", dry_run=True).respond(request)

    project, _manager, worker = _project_with_worker()
    worker.assistant = CapturingAssistant()
    task = Task(
        project_id=project.id,
        title="Implement core runtime",
        goal="Implement core runtime",
        assigned_to=worker.id,
        created_by=project.manager_id,
    )
    project.tasks[task.id] = task

    result = SinglePassStaffWorkflow().run(project, worker, task)
    request = captured["request"]

    assert result.status == TaskStatus.DONE
    assert isinstance(result.task_result, TaskExecutionResult)
    assert result.project_result is None
    assert request.output_contract.name == "TaskExecutionResult"
    assert request.output_schema["title"] == "TaskExecutionResult"
    assert "TaskExecutionResult" in request.messages[-1].content


def test_iterative_workflow_retries_invalid_output_and_succeeds() -> None:
    class InvalidThenValidAssistant:
        """Test fake that returns invalid JSON once, then a valid task result."""

        def __init__(self) -> None:
            self.calls = 0
            self.message_counts: list[int] = []

        def respond(self, request):
            self.calls += 1
            self.message_counts.append(len(request.messages))
            if self.calls == 1:
                return AssistantResponse(content="not json")
            return AssistantResponse(
                content=TaskExecutionResult(
                    summary="Implemented task.",
                    work_performed=["Retried after validation feedback."],
                    deliverables=["Valid task output."],
                    final_output="Valid final output.",
                ).model_dump_json()
            )

    project, _manager, worker = _project_with_worker()
    assistant = InvalidThenValidAssistant()
    worker.assistant = assistant
    task = Task(
        project_id=project.id,
        title="Implement core runtime",
        goal="Implement core runtime",
        assigned_to=worker.id,
        created_by=project.manager_id,
    )
    project.tasks[task.id] = task
    workflow = IterativeStaffWorkflow()

    result = workflow.run(project, worker, task)

    assert result.status == TaskStatus.DONE
    assert result.output == "Valid final output."
    assert assistant.calls == 2
    assert assistant.message_counts[1] == assistant.message_counts[0] + 1
    event_types = [event.type for event in project.events]
    assert "output_validation_failed" in event_types
    assert "workflow_step_started" in event_types
    assert "workflow_step_completed" in event_types


def test_iterative_workflow_executes_tool_call_and_continues() -> None:
    class ToolThenFinalAssistant:
        """Test fake that requests a tool, then returns final structured output."""

        def __init__(self) -> None:
            self.calls = 0
            self.messages: list[list[Message]] = []

        def respond(self, request):
            self.calls += 1
            self.messages.append(list(request.messages))
            if self.calls == 1:
                return AssistantResponse(
                    content="",
                    tool_calls=[ToolCall(id="call_1", tool_name="echo", arguments={"text": "tool output"})],
                    finish_reason="tool_calls",
                )
            assert "tool output" in request.messages[-1].content
            return AssistantResponse(
                content=TaskExecutionResult(
                    summary="Used a tool.",
                    work_performed=["Called echo."],
                    deliverables=["Tool-informed output."],
                    final_output="Final after tool.",
                ).model_dump_json()
            )

    project, _manager, worker = _project_with_worker()
    assistant = ToolThenFinalAssistant()
    worker.assistant = assistant
    task = Task(
        project_id=project.id,
        title="Use tool",
        goal="Use echo tool",
        assigned_to=worker.id,
        created_by=project.manager_id,
    )
    project.tasks[task.id] = task
    workflow = IterativeStaffWorkflow(tool_manager=BuiltinToolManager(enabled_tools=["echo"]))

    result = workflow.run(project, worker, task)

    assert result.status == TaskStatus.DONE
    assert result.output == "Final after tool."
    assert assistant.calls == 2
    event_types = [event.type for event in project.events]
    assert "tool_call_requested" in event_types
    assert "tool_call_completed" in event_types


def test_iterative_workflow_fails_when_tool_limit_is_exceeded() -> None:
    class TooManyToolsAssistant:
        """Test fake that requests more tools than allowed in one step."""

        def respond(self, request):
            return AssistantResponse(
                content="",
                tool_calls=[
                    ToolCall(id="call_1", tool_name="echo", arguments={"text": "one"}),
                    ToolCall(id="call_2", tool_name="echo", arguments={"text": "two"}),
                ],
            )

    project, _manager, worker = _project_with_worker()
    worker.assistant = TooManyToolsAssistant()
    task = Task(
        project_id=project.id,
        title="Use too many tools",
        goal="Use too many tools",
        assigned_to=worker.id,
        created_by=project.manager_id,
    )
    project.tasks[task.id] = task
    workflow_config = parse_project_runtime_config(
        {**_config(), "workflow": {"type": "iterative", "max_tool_calls": 1}}
    ).workflow
    workflow = IterativeStaffWorkflow(
        workflow_config=workflow_config,
        tool_manager=BuiltinToolManager(enabled_tools=["echo"]),
    )

    result = workflow.run(project, worker, task)

    assert result.status == TaskStatus.FAILED
    assert result.error is not None
    assert "max_tool_calls" in result.error.message


def test_iterative_workflow_fails_after_output_retry_limit() -> None:
    class AlwaysInvalidAssistant:
        """Test fake that never satisfies the structured output contract."""

        def respond(self, request):
            return AssistantResponse(content="not json")

    project, _manager, worker = _project_with_worker()
    worker.assistant = AlwaysInvalidAssistant()
    task = Task(
        project_id=project.id,
        title="Implement core runtime",
        goal="Implement core runtime",
        assigned_to=worker.id,
        created_by=project.manager_id,
    )
    project.tasks[task.id] = task
    workflow = IterativeStaffWorkflow(
        workflow_config=parse_project_runtime_config(
            {**_config(), "workflow": {"type": "iterative", "max_steps": 3, "max_output_retries": 1}}
        ).workflow
    )

    result = workflow.run(project, worker, task)

    assert result.status == TaskStatus.FAILED
    assert result.error is not None
    assert "invalid after retries" in result.error.message
    assert any(event.type == "workflow_failed" for event in project.events)


def test_failed_workflow_records_error_events() -> None:
    runtime = create_project_runtime(parse_project_runtime_config(_config()))
    project = runtime.create_project("Plan the project")
    project.manager.assistant = None

    result = runtime.orchestrator.run(project)
    task = _manager_task(project)

    assert result.status == ProjectStatus.FAILED
    assert result.error is not None
    assert result.error.type == "ValueError"
    assert task.status == TaskStatus.FAILED
    assert any(event.type == "workflow_failed" for event in result.events)
    assert any(event.type == "project_failed" for event in result.events)
    assert any(event.type == "task_failed" for event in task.events)


def test_noop_managers_are_safe() -> None:
    staff = Staff(
        id="pm",
        project_id="project",
        name="Ava",
        role="project_manager",
        title="Project Manager",
    )
    task = Task(project_id="project", title="Plan", goal="Plan")

    assert NoopToolManager().list_tools(staff, task) == []
    assert NoopSkillManager().list_skills(staff, task) == []
    assert NoopMemoryManager().retrieve(
        Project(goal="Plan", manager_id="pm", staff={"pm": staff}),
        staff,
        task,
        "Plan",
    ) == []


def test_builtin_tool_manager_echoes_text() -> None:
    result = BuiltinToolManager(enabled_tools=["echo"]).call_tool(
        ToolCall(tool_name="echo", arguments={"text": "hello"})
    )

    assert result.success is True
    assert result.content == "hello"


def test_builtin_tool_manager_reads_workspace_file(tmp_path) -> None:
    file_path = tmp_path / "notes.txt"
    file_path.write_text("project notes", encoding="utf-8")

    result = BuiltinToolManager(workspace_root=tmp_path).call_tool(
        ToolCall(tool_name="read_project_file", arguments={"path": "notes.txt"})
    )

    assert result.success is True
    assert result.content == "project notes"
    assert result.data["path"] == "notes.txt"


def test_builtin_tool_manager_blocks_file_outside_workspace(tmp_path) -> None:
    result = BuiltinToolManager(workspace_root=tmp_path).call_tool(
        ToolCall(tool_name="read_project_file", arguments={"path": "../outside.txt"})
    )

    assert result.success is False
    assert result.error == "path is outside the workspace"


def test_project_result_parser_accepts_valid_json() -> None:
    staff = Staff(
        id="pm",
        project_id="project",
        name="Ava",
        role="project_manager",
        title="Project Manager",
    )
    project = Project(goal="Plan", manager_id="pm", staff={"pm": staff})
    content = OpenAIAssistant(model="test-model", dry_run=True).respond(
        _assistant_request(project, staff)
    ).content

    parsed = ProjectResultOutputParser().parse(content, project)

    assert parsed.summary == "Ava prepared an initial project plan."


def test_project_result_parser_falls_back_on_invalid_json() -> None:
    staff = Staff(
        id="pm",
        project_id="project",
        name="Ava",
        role="project_manager",
        title="Project Manager",
    )
    project = Project(goal="Plan", manager_id="pm", staff={"pm": staff})

    parsed = ProjectResultOutputParser().parse("not json", project)

    assert parsed.project_understanding == "Plan"
    assert parsed.final_output == "not json"
    assert parsed.risks == ["Assistant output required fallback parsing."]


def test_project_result_parser_falls_back_on_partial_json() -> None:
    staff = Staff(
        id="pm",
        project_id="project",
        name="Ava",
        role="project_manager",
        title="Project Manager",
    )
    project = Project(goal="Plan", manager_id="pm", staff={"pm": staff})

    parsed = ProjectResultOutputParser().parse('{"summary": "partial"}', project)

    assert parsed.summary == "Project manager produced an unstructured response."
    assert parsed.final_output == '{"summary": "partial"}'


def test_assistant_config_matches_openai_runtime_options() -> None:
    raw_config = _config()
    raw_config["staff_profiles"]["project_manager"]["assistant"] = {
        "type": "openai",
        "model": "deepseek-v4-pro",
        "api_key": "test-key",
        "base_url": "https://api.deepseek.com",
        "timeout_seconds": 30,
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
        "response_format": {"type": "json_object"},
        "stream": True,
        "tokenlimit": 4096,
        "dry_run": True,
    }

    runtime = create_project_runtime(parse_project_runtime_config(raw_config))
    project = runtime.create_project("Build")
    assistant = project.manager.assistant

    assert isinstance(assistant, OpenAIAssistant)
    assert assistant.model == "deepseek-v4-pro"
    assert assistant.api_key == "test-key"
    assert assistant.base_url == "https://api.deepseek.com"
    assert assistant.timeout_seconds == 30
    assert assistant.thinking == {"type": "enabled"}
    assert assistant.reasoning_effort == "high"
    assert assistant.response_format == {"type": "json_object"}
    assert assistant.stream is True
    assert assistant.token_limit == 4096


def test_openai_assistant_builds_chat_completion_kwargs() -> None:
    staff = Staff(
        id="pm",
        project_id="project",
        name="Ava",
        role="project_manager",
        title="Project Manager",
    )
    project = Project(goal="Plan", manager_id="pm", staff={"pm": staff})
    request = _assistant_request(project, staff)
    assistant = OpenAIAssistant(
        model="deepseek-v4-pro",
        token_limit=4096,
        reasoning_effort="high",
        response_format={"type": "json_object"},
        thinking={"type": "enabled"},
        stream=True,
    )

    kwargs = assistant._chat_completion_kwargs(request)

    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["max_tokens"] == 4096
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    assert kwargs["stream"] is True
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1]["role"] == "user"
    assert "input" not in kwargs
    assert "max_output_tokens" not in kwargs


def test_openai_assistant_disables_reasoning_effort_when_thinking_is_disabled() -> None:
    staff = Staff(
        id="pm",
        project_id="project",
        name="Ava",
        role="project_manager",
        title="Project Manager",
    )
    project = Project(goal="Plan", manager_id="pm", staff={"pm": staff})
    request = _assistant_request(project, staff)
    assistant = OpenAIAssistant(
        model="deepseek-v4-pro",
        reasoning_effort="high",
        thinking={"type": "disabled"},
    )

    kwargs = assistant._chat_completion_kwargs(request)

    assert kwargs["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in kwargs


def test_openai_assistant_extracts_chat_completion_content() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content='{"summary": "ok"}'),
            )
        ]
    )

    content = OpenAIAssistant()._chat_completion_content(response)

    assert content == '{"summary": "ok"}'


def test_openai_assistant_collects_streaming_chat_completion_content() -> None:
    stream = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(delta=SimpleNamespace(content='{"summary": '))
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(delta=SimpleNamespace(content='"ok"}'))
            ]
        ),
    ]

    content = OpenAIAssistant(stream=True)._streaming_chat_completion_content(stream)

    assert content == '{"summary": "ok"}'


def test_openai_assistant_extracts_chat_completion_tool_calls() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_1",
                            function=SimpleNamespace(
                                name="echo",
                                arguments='{"text": "hello"}',
                            ),
                        )
                    ],
                ),
            )
        ]
    )

    assistant = OpenAIAssistant()
    tool_calls = assistant._chat_completion_tool_calls(response)

    assert assistant._chat_completion_finish_reason(response) == "tool_calls"
    assert tool_calls == [ToolCall(id="call_1", tool_name="echo", arguments={"text": "hello"})]


def test_openai_assistant_uses_env_api_key_for_live_mode(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    assistant = OpenAIAssistant()

    assert assistant._effective_api_key() == "env-key"
    assert assistant._should_dry_run() is False


def test_loads_configured_modules() -> None:
    raw_config = _config()
    raw_config["modules"] = ["tests.custom_project_module:register_custom_modules"]
    raw_config["staff_profiles"]["project_manager"]["responsibilities"] = ["research"]
    raw_config["staff_profiles"]["project_manager"]["capabilities"] = ["source_synthesis"]

    runtime = create_project_runtime(parse_project_runtime_config(raw_config))
    project = runtime.create_project("Research")

    assert project.manager.responsibilities[0].name == "research"
    assert project.manager.capabilities[0].name == "source_synthesis"


def test_rejects_unsupported_orchestration_strategy() -> None:
    raw_config = _config()
    raw_config["orchestration"] = {"strategy": "manager_tree"}

    try:
        create_project_runtime(parse_project_runtime_config(raw_config))
    except ValueError as exc:
        assert "unsupported orchestration strategy" in str(exc)
    else:
        raise AssertionError("expected unsupported strategy to fail")


def test_cli_project_run_json(capsys) -> None:
    exit_code = main(
        [
            "project",
            "run",
            "--config",
            "configs/project_runtime.json",
            "--json",
            "Build a project-oriented agent framework",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"status": "done"' in output
    assert '"manager_id": "project_manager"' in output


def test_cli_human_output_hides_events_by_default(capsys) -> None:
    exit_code = main(
        [
            "project",
            "run",
            "--config",
            "configs/project_runtime.json",
            "Build a project-oriented agent framework",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "events:" not in output


def test_cli_human_output_can_show_events(capsys) -> None:
    exit_code = main(
        [
            "project",
            "run",
            "--config",
            "configs/project_runtime.json",
            "--events",
            "Build a project-oriented agent framework",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "events:" in output
    assert "project_created" in output
    assert "workflow_started" in output


def test_cli_human_output_can_show_staffing_matches(capsys) -> None:
    exit_code = main(
        [
            "project",
            "run",
            "--config",
            "configs/project_runtime.json",
            "--staffing-matches",
            "Build a project-oriented agent framework",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "staffing profile matches:" in output
    assert "implementation_staff" in output
    assert "Implementation Staff" in output


def test_cli_reports_config_errors(capsys) -> None:
    exit_code = main(
        [
            "project",
            "run",
            "--config",
            "configs/missing.json",
            "Build a project-oriented agent framework",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "error:" in captured.err
