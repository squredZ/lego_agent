from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from lego_agent.core.models import Project, ProjectResult, StaffRolePlan, StaffingPlan

logger = logging.getLogger(__name__)


class ProjectResultOutputParser:
    """Parses assistant text into a ProjectResult.

    Real model output can be imperfect. The fallback keeps the runtime usable by
    wrapping unstructured output in a valid project result contract.
    """

    def parse(self, content: str, project: Project) -> ProjectResult:
        try:
            raw = json.loads(content)
            parsed = ProjectResult.model_validate(raw)
            logger.debug(
                "assistant output parsed as ProjectResult",
                extra={"project_id": project.id, "content_length": len(content)},
            )
            return parsed
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            logger.warning(
                "assistant output required ProjectResult fallback",
                extra={
                    "project_id": project.id,
                    "content_length": len(content),
                    "error_type": exc.__class__.__name__,
                },
            )
            return self.fallback(content, project)

    def fallback(self, content: str, project: Project) -> ProjectResult:
        logger.debug(
            "building ProjectResult fallback",
            extra={"project_id": project.id, "content_length": len(content)},
        )
        staffing_plan = StaffingPlan(
            required_roles=[
                StaffRolePlan(
                    role="implementation_staff",
                    title="Implementation Staff",
                    responsibilities=["implementation"],
                    capabilities=["execution_planning"],
                    task_focus="Execute project deliverables after planning.",
                    priority=1,
                )
            ],
            rationale="Fallback staffing plan because assistant output was not valid structured JSON.",
        )
        return ProjectResult(
            summary="Project manager produced an unstructured response.",
            project_understanding=project.goal,
            assumptions=[],
            risks=["Assistant output required fallback parsing."],
            staffing_plan=staffing_plan,
            task_breakdown=[],
            execution_plan=[],
            final_output=content,
        )
