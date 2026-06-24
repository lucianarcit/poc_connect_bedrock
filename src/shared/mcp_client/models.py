"""Modelos de dados do cliente MCP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    """Definição de uma tool MCP."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolResult:
    """Resultado da execução de uma tool MCP."""

    tool_name: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: float = 0.0


class MCPClientProtocol:
    """
    Interface abstrata para o cliente MCP.

    Preparada para futura substituição pelo MCP real do cliente.
    """

    def list_tools(self) -> list[ToolDefinition]:
        """Lista as tools disponíveis no servidor."""
        raise NotImplementedError

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Executa uma tool pelo nome com os argumentos fornecidos."""
        raise NotImplementedError
