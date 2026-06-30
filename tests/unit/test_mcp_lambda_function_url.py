"""
Testes do MCP Server handler real (mcp_server.handler.handler).

Valida que o handler exportado funciona com eventos Lambda Function URL v2,
incluindo múltiplas invocações (warm start) sem FunctionError.
"""

import json
import pytest


def _function_url_event(path="/mcp", body="", host="abc123.lambda-url.us-east-1.on.aws"):
    return {
        "version": "2.0", "routeKey": "$default",
        "rawPath": path, "rawQueryString": "",
        "headers": {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            "host": host, "x-forwarded-proto": "https", "x-forwarded-port": "443",
        },
        "requestContext": {
            "accountId": "123456789012", "apiId": "abc123",
            "domainName": host, "domainPrefix": "abc123",
            "http": {"method": "POST", "path": path, "protocol": "HTTP/1.1",
                     "sourceIp": "10.0.0.1", "userAgent": "test"},
            "requestId": "req-123", "routeKey": "$default", "stage": "$default",
            "time": "01/Jan/2025:00:00:00 +0000", "timeEpoch": 1735689600000,
        },
        "body": body, "isBase64Encoded": False,
    }


def _jsonrpc(method, params=None):
    return json.dumps({"jsonrpc": "2.0", "id": "t-1", "method": method, "params": params or {}})


class TestHandlerExport:

    def test_handler_callable(self):
        from mcp_server.handler import handler
        assert callable(handler)

    def test_single_invoke_200(self):
        """Uma invocação retorna 200 para o path correto do MCP instalado."""
        from mcp_server.handler import handler
        # MCP >=1.10 uses Mount at /mcp (requires /mcp/)
        # MCP >=1.28 uses Route at /mcp (requires /mcp)
        # Test both — at least one must return 200
        r1 = handler(_function_url_event("/mcp/", _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        })), None)
        r2 = handler(_function_url_event("/mcp", _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        })), None)
        assert r1["statusCode"] == 200 or r2["statusCode"] == 200, (
            f"/mcp/={r1['statusCode']}, /mcp={r2['statusCode']}. Neither returned 200."
        )

    def test_warm_start_multiple_invocations(self):
        """3 invocações consecutivas funcionam (simula warm start)."""
        from mcp_server.handler import handler
        # Probe to find working path for installed MCP version
        r = handler(_function_url_event("/mcp/", _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1"},
        })), None)
        path = "/mcp/" if r["statusCode"] == 200 else "/mcp"

        for i in range(3):
            resp = handler(_function_url_event(path, _jsonrpc("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": f"w-{i}", "version": "1"},
            })), None)
            assert resp["statusCode"] == 200, f"Invoke {i} on {path}: {resp['statusCode']}"

    def test_each_invocation_creates_new_instances(self):
        """Cada invocação cria instâncias distintas."""
        from mcp_server.handler import _create_app

        apps = []
        for _ in range(3):
            app = _create_app()
            apps.append(id(app))

        assert len(set(apps)) == 3, f"App IDs not unique: {apps}"

    def test_no_unhandled_exception(self):
        """Handler não lança exceção (seria FunctionError: Unhandled)."""
        from mcp_server.handler import handler
        resp = handler(_function_url_event("/mcp/", _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        })), None)
        assert isinstance(resp, dict)
        assert "statusCode" in resp


class TestHandlerRouting:

    def test_mcp_slash_200_with_rawpath(self):
        """POST com rawPath=/mcp/ retorna 200 na produção (Mount) ou /mcp funciona localmente (Route)."""
        from mcp_server.handler import handler
        # Com wrapper, /mcp/ chega ao app. MCP 1.10.1 (Mount) = 200. MCP 1.28 (Route) = 404.
        r_slash = handler(_function_url_event("/mcp/", _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        })), None)
        r_no_slash = handler(_function_url_event("/mcp", _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        })), None)
        # Pelo menos um path deve funcionar
        assert r_slash["statusCode"] == 200 or r_no_slash["statusCode"] == 200, (
            f"/mcp/={r_slash['statusCode']}, /mcp={r_no_slash['statusCode']}"
        )

    def test_mcp_without_slash_rawpath(self):
        """POST com rawPath=/mcp (sem barra) — comportamento depende da versão MCP."""
        from mcp_server.handler import handler
        resp = handler(_function_url_event("/mcp", _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        })), None)
        # MCP 1.28 (Route): 200. MCP 1.10 (Mount): 404. Ambos válidos.
        assert resp["statusCode"] in (200, 404)

    def test_no_redirect(self):
        """Nenhum path retorna 307 (redirect_slashes=False)."""
        from mcp_server.handler import handler
        for path in ["/mcp", "/mcp/"]:
            resp = handler(_function_url_event(path, _jsonrpc("initialize", {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "t", "version": "1"},
            })), None)
            assert resp["statusCode"] != 307, f"Path {path} returned 307"

    def test_root_not_200(self):
        from mcp_server.handler import handler
        resp = handler(_function_url_event("/", _jsonrpc("initialize")), None)
        assert resp["statusCode"] != 200

    def test_wrapper_restores_rawpath(self):
        """FunctionUrlPathWrapper restaura scope.path do rawPath do evento."""
        from mcp_server.handler import FunctionUrlPathWrapper

        captured_paths = []

        class FakeApp:
            state = {}
            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    captured_paths.append(scope["path"])

        wrapper = FunctionUrlPathWrapper(FakeApp())

        import asyncio
        scope = {
            "type": "http",
            "path": "/mcp",  # Mangum normalizou (removeu /)
            "raw_path": b"/mcp",
            "root_path": "",
            "method": "POST",
            "headers": [],
            "query_string": b"",
            "scheme": "https",
            "server": ("localhost", 443),
            "client": ("127.0.0.1", 0),
            "http_version": "1.1",
            "aws.event": {"rawPath": "/mcp/"},  # Original com /
        }

        asyncio.run(wrapper(scope, None, None))
        assert captured_paths == ["/mcp/"]


class TestHandlerProtocol:

    def test_initialize_json_response(self):
        from mcp_server.handler import handler
        # Probe working path
        r = handler(_function_url_event("/mcp/", _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1"},
        })), None)
        path = "/mcp/" if r["statusCode"] == 200 else "/mcp"

        resp = handler(_function_url_event(path, _jsonrpc("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        })), None)
        assert resp["statusCode"] == 200, f"Got {resp['statusCode']}: {resp.get('body','')[:200]}"
        body = json.loads(resp["body"])
        assert body["jsonrpc"] == "2.0"
        assert "serverInfo" in body["result"]
