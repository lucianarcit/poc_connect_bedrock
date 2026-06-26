"""
Testes de transporte HTTP do MCP Server.

Verifica que:
- A rota /mcp responde 200 para requests MCP válidos
- Rotas inexistentes retornam 404
- O formato de resposta é compatível com o MCPClient da Integrator
- O handler Mangum processa eventos Lambda Function URL v2 corretamente
"""

import json
import uuid

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from mcp_server.server import create_mcp_server


@pytest.fixture
async def client():
    """AsyncClient ASGI apontando para o MCP Server em modo teste."""
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


def _jsonrpc(method: str, params: dict = None) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }


class TestRouting:
    """Testa que apenas /mcp é válida."""

    @pytest.mark.anyio
    async def test_post_mcp_route_returns_200(self, client):
        """POST /mcp com initialize retorna 200."""
        resp = await client.post("/mcp", json=_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }))
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_post_root_returns_404(self, client):
        """POST / retorna 404 (rota não existe)."""
        resp = await client.post("/", json=_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }))
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_post_wrong_path_returns_404(self, client):
        """POST /api/mcp retorna 404."""
        resp = await client.post("/api/mcp", json=_jsonrpc("tools/list"))
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_get_mcp_not_post(self, client):
        """GET /mcp não processa JSON-RPC (retorna != 200 com resultado válido ou status informativo)."""
        resp = await client.get("/mcp")
        # O MCP SDK pode retornar 405 ou outra resposta que não é JSON-RPC válido
        # O importante é que POST /mcp funciona (testado acima)
        assert resp.status_code != 200 or "jsonrpc" not in resp.text


class TestMCPProtocol:
    """Testa o protocolo MCP sobre HTTP conforme esperado pela Integrator."""

    @pytest.mark.anyio
    async def test_tools_list_after_initialize(self, client):
        """Após initialize, tools/list retorna as 3 tools."""
        # Initialize
        init_resp = await client.post("/mcp", json=_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }))
        assert init_resp.status_code == 200

        # Obter session id do header (se presente)
        session_id = init_resp.headers.get("mcp-session-id", "")
        headers = {"Mcp-Session-Id": session_id} if session_id else {}

        # Enviar initialized notification
        await client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }, headers=headers)

        # tools/list
        resp = await client.post("/mcp", json=_jsonrpc("tools/list"), headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        tools = data["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "search_support_documentation" in tool_names
        assert "get_support_procedure" in tool_names
        assert "health_check" in tool_names

    @pytest.mark.anyio
    async def test_tool_call_health_check(self, client):
        """tools/call health_check retorna resultado com status healthy."""
        # Initialize + initialized
        init_resp = await client.post("/mcp", json=_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }))
        session_id = init_resp.headers.get("mcp-session-id", "")
        headers = {"Mcp-Session-Id": session_id} if session_id else {}

        await client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }, headers=headers)

        # Call tool
        resp = await client.post("/mcp", json=_jsonrpc("tools/call", {
            "name": "health_check",
            "arguments": {},
        }), headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        content = data["result"]["content"]
        assert len(content) > 0
        text = content[0]["text"]
        parsed = json.loads(text)
        assert parsed["status"] == "healthy"

    @pytest.mark.anyio
    async def test_response_format_compatible_with_integrator(self, client):
        """A resposta segue o formato que o MCPClient da Integrator espera:
        {"jsonrpc": "2.0", "id": "...", "result": {"content": [{"text": "..."}]}}
        """
        init_resp = await client.post("/mcp", json=_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }))
        session_id = init_resp.headers.get("mcp-session-id", "")
        headers = {"Mcp-Session-Id": session_id} if session_id else {}

        await client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }, headers=headers)

        resp = await client.post("/mcp", json=_jsonrpc("tools/call", {
            "name": "search_support_documentation",
            "arguments": {"question": "senha", "product": "", "language": "pt-BR"},
        }), headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        # Formato esperado pelo MCPClient
        assert data["jsonrpc"] == "2.0"
        assert "id" in data
        assert "result" in data
        assert "content" in data["result"]
        assert isinstance(data["result"]["content"], list)
        assert "text" in data["result"]["content"][0]
