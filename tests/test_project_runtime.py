from __future__ import annotations

import logging

from lego_agent.assistants.openai_assistant import OpenAIAssistant
from lego_agent.cli import main
from lego_agent.core.models import (
    AssistantRequest,
    Project,
    ProjectStatus,
    Staff,
    Task,
    TaskStatus,
    WorkContext,
)
from lego_agent.project.config import parse_project_runtime_config
from lego_agent.project.runtime import create_project_runtime
from lego_agent.workflow.managers import NoopMemoryManager, NoopSkillManager, NoopToolManager
from lego_agent.workflow.output import ProjectResultOutputParser
from lego_agent.workflow.staff_workflow import SinglePassStaffWorkflow


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


def test_parses_project_runtime_config() -> None:
    config = parse_project_runtime_config(_config())

    assert config.project.default_manager_profile == "project_manager"
    assert config.orchestration.strategy == "project_manager_only"
    assert config.staff_profiles["project_manager"].assistant.token_limit == 2048


def test_project_manager_only_dry_run_returns_project_result() -> None:
    runtime = create_project_runtime(parse_project_runtime_config(_config()))

    result = runtime.run("Build a project-oriented agent framework")

    assert result.status == ProjectStatus.DONE
    assert result.manager_id == "project_manager"
    assert result.result is not None
    assert result.result.staffing_plan.required_roles
    assert "Build a project-oriented agent framework" in result.result.project_understanding


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
    assert "ProjectResult" in request.messages[-1].content
    assert "Return only valid JSON" in request.messages[-1].content


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
    assert assistant.token_limit == 4096


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
