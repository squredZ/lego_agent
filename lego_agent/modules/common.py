from __future__ import annotations

from lego_agent.core.models import Capability, Responsibility
from lego_agent.core.registry import Registry

responsibilities = Registry[Responsibility]("responsibilities")
capabilities = Registry[Capability]("capabilities")


def register_defaults() -> None:
    defaults = [
        Responsibility(
            name="requirements_analysis",
            description="Clarify project goals, constraints, assumptions, and success criteria.",
        ),
        Responsibility(
            name="planning",
            description="Convert objectives into trackable tasks and milestones.",
        ),
        Responsibility(
            name="staffing",
            description="Identify required project roles and staffing rationale.",
        ),
        Responsibility(
            name="coordination",
            description="Coordinate work, dependencies, communication, and progress.",
        ),
        Responsibility(
            name="acceptance",
            description="Validate outputs against project goals and acceptance criteria.",
        ),
        Responsibility(
            name="implementation",
            description="Build and integrate concrete deliverables.",
        ),
        Responsibility(
            name="review",
            description="Inspect outputs for correctness, risk, and missing evidence.",
        ),
        Responsibility(
            name="testing",
            description="Plan and execute verification activities.",
        ),
    ]
    for item in defaults:
        if responsibilities.maybe_get(item.name) is None:
            responsibilities.register(item.name, item)

    capability_defaults = [
        Capability(
            name="task_decomposition",
            description="Break a goal into executable tasks.",
        ),
        Capability(
            name="staff_recruitment",
            description="Identify staff roles needed for a project.",
        ),
        Capability(name="delegation", description="Assign work to suitable staff roles."),
        Capability(name="code_generation", description="Produce implementation artifacts."),
        Capability(
            name="quality_review",
            description="Evaluate work against acceptance criteria.",
        ),
        Capability(name="execution_planning", description="Create an actionable execution plan."),
    ]
    for item in capability_defaults:
        if capabilities.maybe_get(item.name) is None:
            capabilities.register(item.name, item)
