from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from lego_agent.assistants.openai_assistant import OpenAIAssistant
from lego_agent.core.models import (
    Assistant,
    Project,
    ProjectError,
    ProjectRunResult,
    ProjectStatus,
    Staff,
    Task,
    new_id,
    utc_now,
)
from lego_agent.core.registry import Registry, import_path
from lego_agent.modules.common import capabilities, register_defaults, responsibilities
from lego_agent.project.config import AssistantConfig, ProjectRuntimeConfig, StaffProfileConfig
from lego_agent.project.events import EventRecorder
from lego_agent.project.orchestrator import ProjectManagerOnlyOrchestrator
from lego_agent.project.staffing import StaffProfileResolver
from lego_agent.workflow.staff_workflow import SinglePassStaffWorkflow

AssistantFactory = Callable[[dict[str, object]], Assistant]

logger = logging.getLogger(__name__)
assistant_factories = Registry[AssistantFactory]("assistant_factories")


def register_builtin_factories() -> None:
    """Register assistant implementations shipped by the framework.

    The registry keeps runtime construction configurable: config files refer to
    assistant type names, while the runtime resolves those names into Python
    objects here.
    """
    if assistant_factories.maybe_get("openai") is None:
        assistant_factories.register("openai", lambda options: OpenAIAssistant(**options))
        logger.debug("registered built-in assistant factory", extra={"assistant_type": "openai"})


class ProjectRuntime:
    """High-level entry point for running a project goal.

    Think of this class as the application service. It loads extension modules,
    creates the project aggregate, chooses the orchestrator, and returns a
    `ProjectRunResult` that the CLI or a future API can print directly.
    """

    def __init__(
        self,
        config: ProjectRuntimeConfig,
        workflow: SinglePassStaffWorkflow | None = None,
        event_recorder: EventRecorder | None = None,
    ) -> None:
        logger.debug(
            "initializing project runtime",
            extra={
                "orchestration_strategy": config.orchestration.strategy,
                "module_count": len(config.modules),
                "staff_profile_count": len(config.staff_profiles),
            },
        )
        register_defaults()
        register_builtin_factories()
        _load_modules(config.modules)
        self.config = config
        self.event_recorder = event_recorder or EventRecorder()
        self.workflow = workflow or SinglePassStaffWorkflow(event_recorder=self.event_recorder)
        self.workflow.event_recorder = self.event_recorder
        self.orchestrator = self._create_orchestrator(config.orchestration.strategy)

    def run(self, goal: str) -> ProjectRunResult:
        """Run one project goal from start to finish.

        Version 1 never raises framework errors to the CLI. Unexpected failures
        are converted into a failed `ProjectRunResult`, which makes command-line
        and API callers easier to handle.
        """
        started_at = utc_now()
        logger.info("project run started", extra={"goal_length": len(goal)})
        try:
            project = self.create_project(goal)
            result = self.orchestrator.run(project)
            self._attach_staff_profile_resolution(result)
            result.started_at = started_at
            result.completed_at = result.completed_at or utc_now()
            result.duration_ms = _duration_ms(started_at, result.completed_at)
            logger.info(
                "project run finished",
                extra={
                    "project_id": result.project_id,
                    "status": result.status.value,
                    "duration_ms": result.duration_ms,
                },
            )
            return result
        except Exception as exc:
            completed_at = utc_now()
            logger.exception("project run failed before result creation")
            return ProjectRunResult(
                project_id="",
                project_goal=goal,
                status=ProjectStatus.FAILED,
                manager_id="",
                manager_name="",
                error=ProjectError(type=exc.__class__.__name__, message=str(exc)),
                events=[],
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=_duration_ms(started_at, completed_at),
            )

    def create_project(self, goal: str) -> Project:
        """Create the first project shape: one project and one manager task.

        The project id is created before the manager so every object belongs to
        the same project from the moment it is constructed.
        """
        manager_profile_name = self.config.project.default_manager_profile
        try:
            manager_profile = self.config.staff_profiles[manager_profile_name]
        except KeyError as exc:
            raise ValueError(f"manager profile '{manager_profile_name}' is not configured") from exc

        project_id = new_id()
        manager = self._create_staff(manager_profile, project_id=project_id)
        logger.info(
            "creating project",
            extra={
                "project_id": project_id,
                "manager_profile": manager_profile_name,
                "manager_id": manager.id,
            },
        )
        project = Project(
            id=project_id,
            goal=goal,
            manager_id=manager.id,
            staff={manager.id: manager},
        )
        task = Task(
            project_id=project.id,
            title="Project manager planning task",
            goal=(
                "Analyze the project goal, define assumptions and risks, create a "
                "staffing plan, break down work, propose an execution plan, and "
                "produce an initial project result."
            ),
            assigned_to=manager.id,
            created_by="system",
        )
        project.tasks[task.id] = task
        self.event_recorder.project_event(
            project,
            "project_created",
            "Project created from goal.",
            data={"goal": goal},
        )
        self.event_recorder.project_event(
            project,
            "manager_created",
            f"Primary project manager '{manager.name}' created.",
            actor_id=manager.id,
        )
        self.event_recorder.project_event(
            project,
            "task_created",
            "Project manager planning task created.",
            actor_id="system",
            task_id=task.id,
        )
        self.event_recorder.task_event(
            task,
            "task_created",
            "Project manager planning task created.",
            actor_id="system",
        )
        return project

    def _create_staff(self, profile: StaffProfileConfig, project_id: str) -> Staff:
        """Build a Staff instance from a reusable profile."""
        logger.debug(
            "creating staff from profile",
            extra={
                "project_id": project_id,
                "staff_id": profile.role,
                "role": profile.role,
                "assistant_type": profile.assistant.type,
            },
        )
        assistant = _create_assistant(profile.assistant)
        return Staff(
            id=profile.role,
            project_id=project_id,
            name=profile.name,
            role=profile.role,
            title=profile.title,
            description=profile.description,
            responsibilities=[responsibilities.get(name) for name in profile.responsibilities],
            capabilities=[capabilities.get(name) for name in profile.capabilities],
            assistant=assistant,
        )

    def _create_orchestrator(self, strategy: str) -> ProjectManagerOnlyOrchestrator:
        """Resolve orchestration strategy names from config.

        Only `project_manager_only` is intentionally supported in Version 1.
        More strategies should be added here or through a registry later.
        """
        if strategy != "project_manager_only":
            logger.error("unsupported orchestration strategy", extra={"strategy": strategy})
            raise ValueError(f"unsupported orchestration strategy: {strategy}")
        logger.debug("created orchestrator", extra={"strategy": strategy})
        return ProjectManagerOnlyOrchestrator(self.workflow, self.event_recorder)

    def _attach_staff_profile_resolution(self, result: ProjectRunResult) -> None:
        """Attach staffing profile matches after the PM produces a plan."""
        if result.result is None:
            logger.debug("skipping staff profile resolution because project result is empty")
            return
        resolver = StaffProfileResolver(self.config.staff_profiles, self.config.dynamic_staff)
        result.staffing_profile_resolution = resolver.resolve(result.result.staffing_plan)
        logger.info(
            "staffing profile resolution attached to run result",
            extra={
                "project_id": result.project_id,
                "match_count": len(result.staffing_profile_resolution.matches),
                "unresolved_count": len(result.staffing_profile_resolution.unresolved),
            },
        )


def _create_assistant(config: AssistantConfig) -> Assistant:
    """Create an assistant from config using the assistant registry."""
    logger.debug(
        "creating assistant",
        extra={
            "assistant_type": config.type,
            "model": config.model,
            "dry_run": config.dry_run,
            "has_api_key": config.api_key is not None,
            "has_base_url": config.base_url is not None,
        },
    )
    factory = assistant_factories.get(config.type)
    return factory(config.to_assistant_kwargs())


def _load_modules(paths: list[str]) -> None:
    """Import optional modules so they can register framework extensions."""
    for path in paths:
        logger.info("loading configured module", extra={"module_path": path})
        loaded = import_path(path)
        if callable(loaded):
            loaded()
            logger.debug("called configured module registration hook", extra={"module_path": path})


def _duration_ms(started_at: datetime, completed_at: datetime) -> int:
    return int((completed_at - started_at).total_seconds() * 1000)


def create_project_runtime(config: ProjectRuntimeConfig) -> ProjectRuntime:
    """Convenience factory used by CLI and tests."""
    return ProjectRuntime(config)
