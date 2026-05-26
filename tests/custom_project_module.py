from __future__ import annotations

from lego_agent.core.models import Capability, Responsibility
from lego_agent.modules.common import capabilities, responsibilities


def register_custom_modules() -> None:
    if responsibilities.maybe_get("research") is None:
        responsibilities.register(
            "research",
            Responsibility(
                name="research",
                description="Collect and synthesize source material.",
            ),
        )
    if capabilities.maybe_get("source_synthesis") is None:
        capabilities.register(
            "source_synthesis",
            Capability(
                name="source_synthesis",
                description="Turn source material into decisions.",
            ),
        )
