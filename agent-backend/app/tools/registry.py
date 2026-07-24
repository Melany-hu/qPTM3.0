"""Tool registry — defines JSON schemas for DeepSeek function calling.

Each tool has:
- A JSON schema (sent to DeepSeek as a function definition)
- A Python handler (called when DeepSeek invokes the tool)

The registry maps tool names to their schemas and handlers.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type for tool handler functions
ToolHandler = Callable[..., dict[str, Any]]


class ToolRegistry:
    """Registry of tools available to the LLM agent."""

    def __init__(self) -> None:
        self._schemas: list[dict[str, Any]] = []
        self._handlers: dict[str, ToolHandler] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: ToolHandler,
    ) -> None:
        """Register a tool with its JSON schema and handler."""
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
        self._schemas.append(schema)
        self._handlers[name] = handler
        logger.debug(f"Registered tool: {name}")

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """JSON schemas to pass to DeepSeek's tools parameter."""
        return self._schemas

    def get_handler(self, name: str) -> ToolHandler | None:
        return self._handlers.get(name)

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name with the given arguments."""
        handler = self._handlers.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}
        try:
            result = handler(**arguments)
            logger.info(f"Tool {name} executed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            return {"error": f"Tool execution failed: {e}"}

    @property
    def tool_names(self) -> list[str]:
        return list(self._handlers.keys())

    def schemas_for_tools(self, tool_names: list[str]) -> list[dict[str, Any]]:
        """Return JSON schemas for a subset of tools (plan-step scoped)."""
        allowed = set(tool_names)
        return [
            schema for schema in self._schemas
            if schema["function"]["name"] in allowed
        ]

    def catalog(self) -> list[dict[str, str]]:
        """Tool catalog for the planning layer (no handlers exposed)."""
        return [
            {
                "tool": schema["function"]["name"],
                "description": schema["function"]["description"],
            }
            for schema in self._schemas
        ]


# Global registry
registry = ToolRegistry()
