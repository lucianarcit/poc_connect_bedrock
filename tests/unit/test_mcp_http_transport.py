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
    """Testa rotas do MCP Server. Rota registrada: /mcp (sem barra final)."""

    @pytest.mark.anyio
    async def test_post_mcp_returns_200(self, client):
        """POST /mcp (rota registrada) retorna 200."""
        resp = await client.post("/mcp", json=_jsonrpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0"},
        }))
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_post_mcp_with_slash_redirects_to_mcp(self, client):
        """POST /mcp/ (com barra extra) retorna 307 redirect para /mcp."""
        from httpx import ASGITransport, AsyncClient
        from asgi_lifespan import LifespanManager
        from mcp_server.server import create_mcp_server

        server = create_mcp_server(environment="test")
        app = server.streamable_http_app()
        async with LifespanManager(app) as manager:
            transport = ASGITransport(app=manager.app)
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                follow_redirects=False,
            ) as no_redirect_client:
                resp = await no_redirect_client.post("/mcp/", json=_jsonrpc("initialize", {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                }))
                assert resp.status_code == 307
                location = resp.headers.get("location", "")
                assert location.endswith("/mcp")

    @pytest.mark.anyio
    async def test_post_root_returns_404(self, client):
        """POST / retorna 404."""
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
        """GET /mcp não retorna resultado JSON-RPC."""
        resp = await client.get("/mcp")
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


class TestMCPClientRedirectHandling:
    """Testa o redirect controlado com nova assinatura SigV4."""

    def _mock_httpx_sequence(self, responses):
        """Mock httpx.Client que retorna respostas em sequência."""
        from unittest.mock import MagicMock
        call_count = {"n": 0}
        mock_client_cls = MagicMock()
        mock_ctx = MagicMock()

        def side_effect(*args, **kwargs):
            idx = min(call_count["n"], len(responses) - 1)
            call_count["n"] += 1
            return responses[idx]

        mock_ctx.post.side_effect = side_effect
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
        return mock_client_cls, mock_ctx

    def test_307_same_origin_followed_then_200(self):
        """307 same-origin: segue redirect e retorna resultado."""
        import httpx
        from unittest.mock import patch
        from shared.mcp_client.client import MCPClient

        redirect_resp = httpx.Response(
            status_code=307,
            headers={"location": "https://abc.on.aws/mcp", "content-type": "text/plain"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        success_resp = httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            json={"jsonrpc": "2.0", "id": "1", "result": {"content": [{"text": '{"status":"healthy"}'}]}},
            request=httpx.Request("POST", "https://abc.on.aws/mcp"),
        )
        mock_cls, mock_ctx = self._mock_httpx_sequence([redirect_resp, success_resp])

        client = MCPClient(server_url="https://abc.on.aws/mcp/", max_retries=0)
        client._initialized = True

        with patch("httpx.Client", mock_cls):
            result = client.call_tool("health_check", {})

        assert result.success is True
        assert mock_ctx.post.call_count == 2

    def test_308_same_origin_followed_then_200(self):
        """308 same-origin: segue redirect e retorna resultado."""
        import httpx
        from unittest.mock import patch
        from shared.mcp_client.client import MCPClient

        redirect_resp = httpx.Response(
            status_code=308,
            headers={"location": "/mcp", "content-type": "text/plain"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        success_resp = httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            json={"jsonrpc": "2.0", "id": "1", "result": {"content": [{"text": '{"ok":true}'}]}},
            request=httpx.Request("POST", "https://abc.on.aws/mcp"),
        )
        mock_cls, mock_ctx = self._mock_httpx_sequence([redirect_resp, success_resp])

        client = MCPClient(server_url="https://abc.on.aws/mcp/", max_retries=0)
        client._initialized = True

        with patch("httpx.Client", mock_cls):
            result = client.call_tool("test_tool", {})

        assert result.success is True

    def test_new_sigv4_signature_on_redirect(self):
        """O redirect deve gerar NOVA assinatura (segunda chamada a sign_headers)."""
        import httpx
        from unittest.mock import patch, MagicMock
        from shared.mcp_client.client import MCPClient

        redirect_resp = httpx.Response(
            status_code=307,
            headers={"location": "https://abc.on.aws/mcp", "content-type": "text/plain"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        success_resp = httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            json={"jsonrpc": "2.0", "id": "1", "result": {"content": [{"text": '{}'}]}},
            request=httpx.Request("POST", "https://abc.on.aws/mcp"),
        )
        mock_cls, _ = self._mock_httpx_sequence([redirect_resp, success_resp])

        mock_signer = MagicMock()
        mock_signer.sign_headers.side_effect = lambda **kwargs: kwargs["headers"]

        client = MCPClient(server_url="https://abc.on.aws/mcp/", max_retries=0, sigv4_auth=mock_signer)
        client._initialized = True

        with patch("httpx.Client", mock_cls):
            client.call_tool("test", {})

        # sign_headers chamado 2x: uma para URL original, outra para redirect
        assert mock_signer.sign_headers.call_count == 2
        urls_signed = [c.kwargs["url"] for c in mock_signer.sign_headers.call_args_list]
        assert urls_signed[0] == "https://abc.on.aws/mcp/"
        assert urls_signed[1] == "https://abc.on.aws/mcp"

    def test_body_and_method_preserved_on_redirect(self):
        """Body JSON-RPC e método POST preservados no redirect."""
        import httpx
        from unittest.mock import patch
        from shared.mcp_client.client import MCPClient

        redirect_resp = httpx.Response(
            status_code=307,
            headers={"location": "https://abc.on.aws/mcp"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        success_resp = httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            json={"jsonrpc": "2.0", "id": "1", "result": {"content": [{"text": '{}'}]}},
            request=httpx.Request("POST", "https://abc.on.aws/mcp"),
        )
        mock_cls, mock_ctx = self._mock_httpx_sequence([redirect_resp, success_resp])

        client = MCPClient(server_url="https://abc.on.aws/mcp/", max_retries=0)
        client._initialized = True

        with patch("httpx.Client", mock_cls):
            client.call_tool("health_check", {})

        # Both calls should be POST with content (body)
        for call in mock_ctx.post.call_args_list:
            assert "content" in call.kwargs
            assert len(call.kwargs["content"]) > 0

    def test_session_id_preserved_on_redirect(self):
        """Mcp-Session-Id preservado no redirect."""
        import httpx
        from unittest.mock import patch, MagicMock
        from shared.mcp_client.client import MCPClient

        redirect_resp = httpx.Response(
            status_code=307,
            headers={"location": "https://abc.on.aws/mcp"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        success_resp = httpx.Response(
            status_code=200,
            headers={"content-type": "application/json", "mcp-session-id": "sess-123"},
            json={"jsonrpc": "2.0", "id": "1", "result": {"content": [{"text": '{}'}]}},
            request=httpx.Request("POST", "https://abc.on.aws/mcp"),
        )
        mock_cls, mock_ctx = self._mock_httpx_sequence([redirect_resp, success_resp])

        client = MCPClient(server_url="https://abc.on.aws/mcp/", max_retries=0)
        client._initialized = True
        client._session_id = "existing-session"

        with patch("httpx.Client", mock_cls):
            client.call_tool("test", {})

        # Verify session header was sent in both requests
        for call in mock_ctx.post.call_args_list:
            headers = call.kwargs.get("headers", {})
            assert "Mcp-Session-Id" in headers
            assert headers["Mcp-Session-Id"] == "existing-session"

    def test_redirect_to_different_host_rejected(self):
        """Redirect para host diferente é rejeitado."""
        import httpx
        from unittest.mock import patch
        from shared.mcp_client.client import MCPClient

        redirect_resp = httpx.Response(
            status_code=307,
            headers={"location": "https://evil.com/mcp"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        mock_cls, _ = self._mock_httpx_sequence([redirect_resp])

        client = MCPClient(server_url="https://abc.on.aws/mcp/", max_retries=0)
        client._initialized = True

        with patch("httpx.Client", mock_cls):
            result = client.call_tool("test", {})

        assert result.success is False
        assert "different host" in result.error

    def test_redirect_loop_detected(self):
        """Segundo redirect (loop) gera erro explícito."""
        import httpx
        from unittest.mock import patch
        from shared.mcp_client.client import MCPClient

        redirect1 = httpx.Response(
            status_code=307,
            headers={"location": "https://abc.on.aws/mcp"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        redirect2 = httpx.Response(
            status_code=307,
            headers={"location": "https://abc.on.aws/mcp/"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp"),
        )
        mock_cls, _ = self._mock_httpx_sequence([redirect1, redirect2])

        client = MCPClient(server_url="https://abc.on.aws/mcp/", max_retries=0)
        client._initialized = True

        with patch("httpx.Client", mock_cls):
            result = client.call_tool("test", {})

        assert result.success is False
        assert "loop" in result.error.lower()

    def test_missing_location_header_error(self):
        """307 sem Location gera erro claro."""
        import httpx
        from unittest.mock import patch
        from shared.mcp_client.client import MCPClient

        redirect_resp = httpx.Response(
            status_code=307,
            headers={"content-type": "text/plain"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        mock_cls, _ = self._mock_httpx_sequence([redirect_resp])

        client = MCPClient(server_url="https://abc.on.aws/mcp/", max_retries=0)
        client._initialized = True

        with patch("httpx.Client", mock_cls):
            result = client.call_tool("test", {})

        assert result.success is False
        assert "Location" in result.error

    def test_self_referential_redirect_allowed_once(self):
        """Location = URL original: permite uma tentativa, se repetir = loop."""
        import httpx
        from unittest.mock import patch
        from shared.mcp_client.client import MCPClient

        # Location aponta para a mesma URL
        redirect1 = httpx.Response(
            status_code=307,
            headers={"location": "https://abc.on.aws/mcp/"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        # Segunda também redireciona (loop)
        redirect2 = httpx.Response(
            status_code=307,
            headers={"location": "https://abc.on.aws/mcp/"},
            request=httpx.Request("POST", "https://abc.on.aws/mcp/"),
        )
        mock_cls, _ = self._mock_httpx_sequence([redirect1, redirect2])

        client = MCPClient(server_url="https://abc.on.aws/mcp/", max_retries=0)
        client._initialized = True

        with patch("httpx.Client", mock_cls):
            result = client.call_tool("test", {})

        assert result.success is False
        assert "loop" in result.error.lower()

    def test_url_not_stripped(self):
        """MCPClient preserva a URL exata (sem rstrip)."""
        from shared.mcp_client.client import MCPClient

        c1 = MCPClient(server_url="http://host/mcp")
        assert c1._server_url == "http://host/mcp"

        c2 = MCPClient(server_url="http://host/mcp/")
        assert c2._server_url == "http://host/mcp/"
