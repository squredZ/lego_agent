from __future__ import annotations

import logging

from lego_agent.core.models import (
    StaffProfileMatch,
    StaffProfileResolution,
    StaffingPlan,
)
from lego_agent.project.config import StaffProfileConfig

logger = logging.getLogger(__name__)


class StaffProfileResolver:
    """Matches planned staff roles to configured reusable staff profiles.

    Version 1 only reports these matches. Version 2 can reuse the same class
    before creating recruited `Staff` objects from matching profiles.
    """

    def __init__(self, profiles: dict[str, StaffProfileConfig]) -> None:
        self.profiles = profiles

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
            logger.warning("staff profile unresolved", extra={"planned_role": planned_role})
            return StaffProfileMatch(
                planned_role=planned_role,
                planned_title=planned_title,
                matched=False,
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
            profile_name=profile_name,
            profile_role=profile.role,
            profile_title=profile.title,
            reason=f"Matched planned role '{planned_role}' to configured profile '{profile_name}'.",
        )

    def _profile_name_for_role(self, planned_role: str) -> str | None:
        if planned_role in self.profiles:
            return planned_role
        for profile_name, profile in self.profiles.items():
            if profile.role == planned_role:
                return profile_name
        return None
