from __future__ import annotations

from typing import Any, Awaitable, Callable

from src.onboarding.domain.models import ToolNotAllowed


Tool = Callable[..., Awaitable[Any]]


class ControlledToolRegistry:
    """Punto único de invocación: una herramienta no autorizada nunca se ejecuta."""

    def __init__(self, tools: dict[str, Tool], allowlists: dict[str, set[str]]) -> None:
        self._tools = tools
        self._allowlists = allowlists

    async def invoke(self, agent: str, tool_name: str, **kwargs: Any) -> Any:
        allowed = self._allowlists.get(agent, set())
        if tool_name not in allowed:
            raise ToolNotAllowed(
                f"El agente '{agent}' no tiene permitido usar '{tool_name}'"
            )
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Herramienta no registrada: {tool_name}")
        return await tool(**kwargs)

    def allowed_tools(self, agent: str) -> frozenset[str]:
        return frozenset(self._allowlists.get(agent, set()))

