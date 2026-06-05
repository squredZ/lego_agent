"""Public compatibility exports for core domain models.

The model implementation is split by responsibility inside this package, while
callers can keep importing from `lego_agent.core.models`.
"""

from lego_agent.core.models.assistant import (
    Assistant,
    AssistantResponse,
    Message,
    OutputContract,
)
from lego_agent.core.models.base import new_id, utc_now
from lego_agent.core.models.capabilities import Capability, Responsibility
from lego_agent.core.models.control import (
    ManagerAction,
    ManagerDecision,
    ProjectSnapshot,
    StaffMessageSnapshot,
    StaffSnapshot,
    TaskSnapshot,
)
from lego_agent.core.models.enums import EventLevel, ProjectStatus, StaffStatus, TaskStatus
from lego_agent.core.models.errors import ProjectError, TaskError
from lego_agent.core.models.events import ProjectEvent, TaskEvent
from lego_agent.core.models.memory import MemoryItem
from lego_agent.core.models.messages import StaffInbox, StaffMessage, StaffMessageType
from lego_agent.core.models.project import Project, ProjectRunResult
from lego_agent.core.models.skills import SkillSpec
from lego_agent.core.models.staff import Staff
from lego_agent.core.models.staffing import (
    ProjectResult,
    StaffProfileMatch,
    StaffProfileResolution,
    StaffRolePlan,
    StaffingPlan,
    TaskExecutionResult,
)
from lego_agent.core.models.task import Task
from lego_agent.core.models.tools import ToolCall, ToolResult, ToolSpec
from lego_agent.core.models.workflow import AssistantRequest, WorkContext, WorkResult

__all__ = [
    "Assistant",
    "AssistantRequest",
    "AssistantResponse",
    "Capability",
    "EventLevel",
    "ManagerAction",
    "ManagerDecision",
    "MemoryItem",
    "Message",
    "OutputContract",
    "Project",
    "ProjectError",
    "ProjectEvent",
    "ProjectResult",
    "ProjectRunResult",
    "ProjectSnapshot",
    "ProjectStatus",
    "Responsibility",
    "SkillSpec",
    "Staff",
    "StaffInbox",
    "StaffMessage",
    "StaffMessageSnapshot",
    "StaffMessageType",
    "StaffProfileMatch",
    "StaffProfileResolution",
    "StaffRolePlan",
    "StaffSnapshot",
    "StaffStatus",
    "StaffingPlan",
    "Task",
    "TaskError",
    "TaskEvent",
    "TaskExecutionResult",
    "TaskSnapshot",
    "TaskStatus",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "WorkContext",
    "WorkResult",
    "new_id",
    "utc_now",
]
