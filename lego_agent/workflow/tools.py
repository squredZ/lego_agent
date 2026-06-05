from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol

from lego_agent.core.models import ToolCall, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class Tool(Protocol):
    """Small contract every executable tool must satisfy.

    A tool owns one concrete action. Workflows never call tools directly; they
    ask a ToolManager to execute a ToolCall, and the manager delegates to a
    registered Tool implementation.
    """

    name: str
    description: str
    parameters_schema: dict[str, Any]

    def call(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the tool with model-provided arguments."""


class ToolRegistry:
    """Stores available tools by name.

    The registry is the extension point for built-in and custom tools. Adding a
    tool should mean registering another Tool object, not editing workflow or
    manager code.
    """

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        """Add or replace a tool by its stable name."""
        self._tools[tool.name] = tool
        logger.debug("tool registered", extra={"tool_name": tool.name})

    def get(self, name: str) -> Tool | None:
        """Return a registered tool, or None when the name is unknown."""
        return self._tools.get(name)

    def names(self) -> list[str]:
        """Return registered names in deterministic order for tests and logs."""
        return sorted(self._tools)

    def list_specs(self, enabled_tools: set[str]) -> list[ToolSpec]:
        """Build assistant-facing tool specs for enabled registered tools."""
        return [
            ToolSpec(
                name=tool.name,
                description=tool.description,
                parameters_schema=tool.parameters_schema,
            )
            for name, tool in sorted(self._tools.items())
            if name in enabled_tools
        ]

    def call(self, call: ToolCall) -> ToolResult:
        """Execute a registered tool call and normalize unknown-tool failures."""
        tool = self.get(call.tool_name)
        if tool is None:
            return ToolResult(
                tool_name=call.tool_name,
                success=False,
                error=f"tool '{call.tool_name}' is not implemented",
            )
        return tool.call(call.arguments)


class EchoTool:
    """Returns the provided text.

    This intentionally tiny tool gives tests a deterministic way to verify the
    full assistant -> tool -> assistant loop without touching the filesystem.
    """

    name = "echo"
    description = "Return the provided text. Useful for deterministic tool-loop tests."
    parameters_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def call(self, arguments: dict[str, Any]) -> ToolResult:
        text = arguments.get("text", "")
        content = str(text)
        logger.info("builtin echo completed", extra={"content_length": len(content)})
        return ToolResult(tool_name=self.name, success=True, content=content)


class ReadProjectFileTool:
    """Reads a UTF-8 text file inside a configured workspace.

    The workspace boundary prevents model-provided paths from reading files
    outside the project directory. Logs include relative paths and sizes, not
    file contents.
    """

    name = "read_project_file"
    description = "Read a UTF-8 text file inside the current workspace."
    parameters_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def __init__(self, workspace_root: Path | str | None = None) -> None:
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()

    def call(self, arguments: dict[str, Any]) -> ToolResult:
        raw_path = arguments.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="'path' must be a non-empty string",
            )

        candidate = (self.workspace_root / raw_path).resolve()
        if not self._is_inside_workspace(candidate):
            logger.warning("blocked file read outside workspace", extra={"tool_name": self.name})
            return ToolResult(
                tool_name=self.name,
                success=False,
                error="path is outside the workspace",
            )

        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
            )

        relative_path = str(candidate.relative_to(self.workspace_root))
        logger.info(
            "builtin read_project_file completed",
            extra={"path": relative_path, "content_length": len(content)},
        )
        return ToolResult(
            tool_name=self.name,
            success=True,
            content=content,
            data={"path": relative_path},
        )

    def _is_inside_workspace(self, path: Path) -> bool:
        """Return True only for files under the configured workspace root."""
        return path == self.workspace_root or self.workspace_root in path.parents


def create_builtin_tool_registry(workspace_root: Path | str | None = None) -> ToolRegistry:
    """Create the default registry used by `BuiltinToolManager`."""
    return ToolRegistry(
        [
            EchoTool(),
            ReadProjectFileTool(workspace_root=workspace_root),
        ]
    )
