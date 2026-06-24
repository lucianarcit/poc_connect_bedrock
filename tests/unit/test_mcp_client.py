"""Testes do cliente MCP (sucesso, timeout, erro)."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
import httpx

from shared.mcp_client.client import MCPClient
from shared.mcp_client.exceptions import (
    MCPConnectionError,
    MCPServerError,
    MCPTimeoutError,
)
from shared.mcp_client.models import ToolResult


@pytest.fixture
def client() -> MCPClient:
    return MCPClient(server_url="http://fake-mcp:8000/mcp", timeout_seconds=2.0, max_retries=1)


def _mock_httpx(mock_response=None, side_effect=None):
    """Helper para configurar mock do httpx.Client context manager."""
    mock_client_cls = MagicMock()
    mock_ctx = MagicMock()
    if side_effect:
        mock_ctx.post.side_effect = side_effect
    else:
        mock_ctx.post.return_value = mock_response
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
    return mock_client_cls


class TestMCPClientCallTool:
    """Testes de call_tool."""

    def test_success(self, client: MCPClient):
        """Deve retornar ToolResult com sucesso quando server responde OK."""
        mock_response = httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": "123",
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps({"answer": "resposta", "demo": True})}
                    ]
                },
            },
        )
        with patch("httpx.Client", _mock_httpx(mock_response)):
            result = client.call_tool("search_support_documentation", {"question": "teste"})

        assert result.success is True
        assert result.tool_name == "search_support_documentation"
        assert result.data["answer"] == "resposta"
        assert result.latency_ms > 0

    def test_timeout(self, client: MCPClient):
        """Deve retornar ToolResult com sucesso=False em timeout."""
        with patch("httpx.Client", _mock_httpx(side_effect=httpx.TimeoutException("timeout"))):
            result = client.call_tool("health_check", {})

        assert result.success is False
        assert result.error is not None
        assert "timeout" in result.error.lower() or "Timeout" in result.error

    def test_connection_error(self, client: MCPClient):
        """Deve retornar ToolResult com sucesso=False em falha de conexão."""
        with patch("httpx.Client", _mock_httpx(side_effect=httpx.ConnectError("refused"))):
            result = client.call_tool("health_check", {})

        assert result.success is False
        assert result.error is not None
        assert "conectar" in result.error.lower() or "Falha" in result.error

    def test_server_500(self, client: MCPClient):
        """HTTP 500 deve retornar ToolResult com sucesso=False (erro encapsulado)."""
        # MCPServerError é subclass de MCPClientError, capturada no call_tool
        mock_response = httpx.Response(status_code=500, text="Internal Server Error")
        with patch("httpx.Client", _mock_httpx(mock_response)):
            result = client.call_tool("health_check", {})

        assert result.success is False
        assert "500" in result.error

    def test_jsonrpc_error(self, client: MCPClient):
        """JSON-RPC error deve retornar ToolResult com sucesso=False."""
        mock_response = httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": "123",
                "error": {"code": -32601, "message": "Method not found"},
            },
        )
        with patch("httpx.Client", _mock_httpx(mock_response)):
            result = client.call_tool("invalid_tool", {})

        assert result.success is False
        assert "Method not found" in result.error

    def test_non_json_text_content(self, client: MCPClient):
        """Deve tratar conteúdo text não-JSON graciosamente."""
        mock_response = httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": "123",
                "result": {
                    "content": [{"type": "text", "text": "plain text response"}]
                },
            },
        )
        with patch("httpx.Client", _mock_httpx(mock_response)):
            result = client.call_tool("some_tool", {})

        assert result.success is True
        assert result.data == {"raw_response": "plain text response"}

    def test_empty_content(self, client: MCPClient):
        """Deve tratar resposta sem content."""
        mock_response = httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": "123",
                "result": {"content": []},
            },
        )
        with patch("httpx.Client", _mock_httpx(mock_response)):
            result = client.call_tool("some_tool", {})

        assert result.success is True


class TestMCPClientListTools:
    """Testes de list_tools."""

    def test_list_tools_success(self, client: MCPClient):
        """Deve listar tools retornadas pelo servidor."""
        mock_response = httpx.Response(
            status_code=200,
            json={
                "jsonrpc": "2.0",
                "id": "123",
                "result": {
                    "tools": [
                        {"name": "tool_a", "description": "A", "inputSchema": {}},
                        {"name": "tool_b", "description": "B", "inputSchema": {}},
                    ]
                },
            },
        )
        with patch("httpx.Client", _mock_httpx(mock_response)):
            tools = client.list_tools()

        assert len(tools) == 2
        assert tools[0].name == "tool_a"
        assert tools[1].name == "tool_b"
