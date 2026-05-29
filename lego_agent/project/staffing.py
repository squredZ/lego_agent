from __future__ import annotations

import logging
import re
from collections.abc import Callable

from lego_agent.core.models import (
    Assistant,
    Capability,
    Responsibility,
    Staff,
    StaffProfileMatch,
    StaffProfileResolution,
    StaffRolePlan,
    StaffingPlan,
)
from lego_agent.modules.common import capabilities, responsibilities
from lego_agent.project.config import AssistantConfig, DynamicStaffConfig, StaffProfileConfig

logger = logging.getLogger(__name__)


def normalize_staff_role_id(raw_role: str) -> str:
    """Convert model-generated role text into a stable internal identifier.

    LLMs often return human labels such as "Frontend Developer". Runtime state,
    task assignment, messages, and future persistence need a predictable id, so
    dynamic roles are normalized to lowercase snake_case while display titles
    keep the original human-readable text.
    """
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", raw_role.strip().lower()).strip("_")
    return normalized or "staff"


class StaffProfileResolver:
    """Resolves planned roles to profile templates or dynamic staff creation.

    Profiles are templates, not a whitelist. If a project manager plans a role
    that has no configured profile, dynamic staff creation can still proceed.
    """

    def __init__(
        self,
        profiles: dict[str, StaffProfileConfig],
        dynamic_staff: DynamicStaffConfig,
    ) -> None:
        self.profiles = profiles
        self.dynamic_staff = dynamic_staff

    def resolve(self, staffing_plan: StaffingPlan) -> StaffProfileResolution:
        """Resolve every planned role in priority order."""
        matches = [
            self._resolve_role(planned_role.role, planned_role.title)
            for planned_role in sorted(staffing_plan.required_roles, key=lambda item: item.priority)
        ]
        resolution = StaffProfileResolution(matches=matches)
        logger.info(
            "staff profile resolution completed",
            extra={
                "match_count": len(resolution.matches),
                "unresolved_count": len(resolution.unresolved),
            },
        )
        return resolution

    def _resolve_role(self, planned_role: str, planned_title: str) -> StaffProfileMatch:
        """Match by profile key first, then by profile role field."""
        profile_name = self._profile_name_for_role(planned_role)
        if profile_name is None:
            if self.dynamic_staff.enabled:
                logger.info("staff role will be created dynamically", extra={"planned_role": planned_role})
                return StaffProfileMatch(
                    planned_role=planned_role,
                    planned_title=planned_title,
                    matched=True,
                    source="dynamic",
                    reason=f"Planned role '{planned_role}' will be created dynamically from the staffing plan.",
                )
            logger.warning("staff profile unresolved", extra={"planned_role": planned_role})
            return StaffProfileMatch(
                planned_role=planned_role,
                planned_title=planned_title,
                matched=False,
                source="unresolved",
                reason=f"No configured staff profile matches planned role '{planned_role}'.",
            )

        profile = self.profiles[profile_name]
        logger.debug(
            "staff profile matched",
            extra={
                "planned_role": planned_role,
                "profile_name": profile_name,
                "profile_role": profile.role,
            },
        )
        return StaffProfileMatch(
            planned_role=planned_role,
            planned_title=planned_title,
            matched=True,
            source="profile",
            profile_name=profile_name,
            profile_role=profile.role,
            profile_title=profile.title,
            reason=f"Matched planned role '{planned_role}' to configured profile '{profile_name}'.",
        )

    def _profile_name_for_role(self, planned_role: str) -> str | None:
        normalized_role = normalize_staff_role_id(planned_role)
        if planned_role in self.profiles:
            return planned_role
        if normalized_role in self.profiles:
            return normalized_role
        for profile_name, profile in self.profiles.items():
            if profile.role == planned_role or normalize_staff_role_id(profile.role) == normalized_role:
                return profile_name
        return None


class StaffFactory:
    """Creates project staff from configured profiles or AI-generated plans."""

    def __init__(
        self,
        profiles: dict[str, StaffProfileConfig],
        dynamic_staff: DynamicStaffConfig,
        assistant_factory: Callable[[AssistantConfig], Assistant],
    ) -> None:
        self.profiles = profiles
        self.dynamic_staff = dynamic_staff
        self.assistant_factory = assistant_factory

    def create_from_plan(
        self,
        role_plan: StaffRolePlan,
        project_id: str,
        *,
        manager_id: str,
    ) -> Staff:
        """Create one staff member from a staffing-plan role.

        Configured profiles provide reusable templates. Dynamic creation uses
        the role plan itself and the default dynamic assistant config.
        """
        profile = self._profile_for_role(role_plan.role)
        if profile is not None:
            return self._from_profile(profile, project_id=project_id, manager_id=manager_id)
        return self._from_dynamic_plan(role_plan, project_id=project_id, manager_id=manager_id)

    def _from_profile(self, profile: StaffProfileConfig, *, project_id: str, manager_id: str) -> Staff:
        logger.info(
            "creating staff from configured profile",
            extra={"project_id": project_id, "staff_id": profile.role, "profile_role": profile.role},
        )
        return Staff(
            id=profile.role,
            project_id=project_id,
            name=profile.name,
            role=profile.role,
            title=profile.title,
            description=profile.description,
            responsibilities=[responsibilities.get(name) for name in profile.responsibilities],
            capabilities=[capabilities.get(name) for name in profile.capabilities],
            assistant=self.assistant_factory(profile.assistant),
            manager_id=manager_id,
        )

    def _from_dynamic_plan(
        self,
        role_plan: StaffRolePlan,
        *,
        project_id: str,
        manager_id: str,
    ) -> Staff:
        if not self.dynamic_staff.enabled:
            raise ValueError(f"dynamic staff creation is disabled for role '{role_plan.role}'")
        staff_id = normalize_staff_role_id(role_plan.role)
        logger.info(
            "creating staff dynamically from staffing plan",
            extra={
                "project_id": project_id,
                "staff_id": staff_id,
                "planned_role": role_plan.role,
            },
        )
        return Staff(
            id=staff_id,
            project_id=project_id,
            name=role_plan.title,
            role=staff_id,
            title=role_plan.title,
            metadata={"planned_role": role_plan.role},
            responsibilities=[
                self._responsibility_from_plan(name)
                for name in role_plan.responsibilities
            ],
            capabilities=[
                self._capability_from_plan(name)
                for name in role_plan.capabilities
            ],
            assistant=self.assistant_factory(self.dynamic_staff.default_assistant),
            manager_id=manager_id,
        )

    def _profile_for_role(self, role: str) -> StaffProfileConfig | None:
        normalized_role = normalize_staff_role_id(role)
        if role in self.profiles:
            return self.profiles[role]
        if normalized_role in self.profiles:
            return self.profiles[normalized_role]
        for profile in self.profiles.values():
            if profile.role == role or normalize_staff_role_id(profile.role) == normalized_role:
                return profile
        return None

    def _responsibility_from_plan(self, name: str) -> Responsibility:
        existing = responsibilities.maybe_get(name)
        if existing is not None:
            return existing
        if not self.dynamic_staff.allow_dynamic_responsibilities:
            raise KeyError(f"responsibility '{name}' is not configured")
        return Responsibility(name=name, description=name)

    def _capability_from_plan(self, name: str) -> Capability:
        existing = capabilities.maybe_get(name)
        if existing is not None:
            return existing
        if not self.dynamic_staff.allow_dynamic_capabilities:
            raise KeyError(f"capability '{name}' is not configured")
        return Capability(name=name, description=name)
