"""Testes do MCP Server (inicialização e chamada de tools via ASGI)."""

from __future__ import annotations

import json
import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from mcp_server.server import create_mcp_server


@pytest.fixture
async def client():
    """Cria um AsyncClient com lifespan gerenciado para o app ASGI."""
    server = create_mcp_server(environment="test")
    app = server.streamable_http_app()
    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        ) as ac:
            yield ac


def _jsonrpc(method: str, params: dict | None = None) -> dict:
    """Cria um payload JSON-RPC 2.0."""
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }


async def _initialize(client: AsyncClient) -> None:
    """Envia initialize ao server."""
    await client.post(
        "/mcp",
        json=_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }),
    )


@pytest.mark.anyio
async def test_initialize(client: AsyncClient):
    """Deve responder ao initialize do protocolo MCP."""
    resp = await client.post(
        "/mcp",
        json=_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert "serverInfo" in data["result"]


@pytest.mark.anyio
async def test_list_tools(client: AsyncClient):
    """Deve listar as 3 tools registradas."""
    await _initialize(client)
    resp = await client.post("/mcp", json=_jsonrpc("tools/list"))

    assert resp.status_code == 200
    data = resp.json()
    tools = data["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    assert "search_support_documentation" in tool_names
    assert "get_support_procedure" in tool_names
    assert "health_check" in tool_names
    assert len(tools) == 3


@pytest.mark.anyio
async def test_call_search_support_documentation(client: AsyncClient):
    """Deve executar search_support_documentation e retornar resultado."""
    await _initialize(client)
    resp = await client.post(
        "/mcp",
        json=_jsonrpc("tools/call", {
            "name": "search_support_documentation",
            "arguments": {"question": "como redefinir minha senha"},
        }),
    )

    assert resp.status_code == 200
    data = resp.json()
    content = data["result"]["content"]
    assert len(content) > 0
    result_data = json.loads(content[0]["text"])
    assert result_data["document_id"] == "DOC-001"
    assert result_data["demo"] is True


@pytest.mark.anyio
async def test_call_get_support_procedure(client: AsyncClient):
    """Deve executar get_support_procedure e retornar passos."""
    await _initialize(client)
    resp = await client.post(
        "/mcp",
        json=_jsonrpc("tools/call", {
            "name": "get_support_procedure",
            "arguments": {"procedure_id": "PROC-001"},
        }),
    )

    assert resp.status_code == 200
    data = resp.json()
    content = data["result"]["content"]
    result_data = json.loads(content[0]["text"])
    assert result_data["procedure_id"] == "PROC-001"
    assert len(result_data["steps"]) > 0


@pytest.mark.anyio
async def test_call_health_check(client: AsyncClient):
    """Deve executar health_check e retornar status healthy."""
    await _initialize(client)
    resp = await client.post(
        "/mcp",
        json=_jsonrpc("tools/call", {
            "name": "health_check",
            "arguments": {},
        }),
    )

    assert resp.status_code == 200
    data = resp.json()
    content = data["result"]["content"]
    result_data = json.loads(content[0]["text"])
    assert result_data["status"] == "healthy"
    assert result_data["documents_loaded"] == 5


@pytest.mark.anyio
async def test_call_search_fallback(client: AsyncClient):
    """Deve retornar fallback quando nenhum documento é encontrado."""
    await _initialize(client)
    resp = await client.post(
        "/mcp",
        json=_jsonrpc("tools/call", {
            "name": "search_support_documentation",
            "arguments": {"question": "xyz algo completamente irrelevante"},
        }),
    )

    assert resp.status_code == 200
    data = resp.json()
    content = data["result"]["content"]
    result_data = json.loads(content[0]["text"])
    assert result_data["document_id"] is None
    assert result_data["confidence"] == 0.0
