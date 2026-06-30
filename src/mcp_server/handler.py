"""
Handler Lambda para o MCP Server.

Usa Mangum para adaptar a aplicação ASGI (FastMCP/Starlette) para o
formato de evento da Lambda Function URL.

Stack: Lambda Function URL → Mangum → FunctionUrlPathWrapper → Starlette (FastMCP) → JSON-RPC → Tools

Fix crítico: Mangum normaliza rawPath="/mcp/" para scope.path="/mcp" (remove trailing slash).
O MCP SDK 1.10.1 registra a rota como Mount em "/mcp", que requer scope.path="/mcp/" para match.
O FunctionUrlPathWrapper restaura scope["path"] a partir de scope["aws.event"]["rawPath"].
"""

import logging
import time
from typing import Any

from mangum import Mangum

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class FunctionUrlPathWrapper:
    """
    Wrapper ASGI que restaura o path original do Lambda Function URL.

    Mangum normaliza o path (remove trailing slash via unquote/strip).
    O MCP SDK 1.10.1 usa Mount que requer trailing slash para match.
    Este wrapper restaura scope["path"] a partir de aws.event.rawPath.
    """

    def __init__(self, app):
        self.app = app
        self.state = getattr(app, "state", {})

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            event = scope.get("aws.event", {})
            raw_path = event.get("rawPath") if isinstance(event, dict) else None
            if raw_path and raw_path != scope.get("path"):
                scope = dict(scope)
                scope["path"] = raw_path
                scope["raw_path"] = raw_path.encode("utf-8")

        await self.app(scope, receive, send)


def _create_app():
    """Cria app ASGI fresco com FunctionUrlPathWrapper."""
    from mcp_server.server import create_mcp_server

    server = create_mcp_server(environment="production")
    app = server.streamable_http_app()
    app.router.redirect_slashes = False
    return FunctionUrlPathWrapper(app)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler — cria FastMCP + app + Mangum frescos a cada invocação.
    """
    start = time.monotonic()
    raw_path = event.get("rawPath") if isinstance(event, dict) else None
    request_id = getattr(context, "aws_request_id", "local") if context else "local"

    print(f"MCP handler_start raw_path={raw_path} request_id={request_id}", flush=True)

    try:
        app = _create_app()
        print(f"MCP app_created elapsed={int((time.monotonic()-start)*1000)}ms", flush=True)

        asgi_handler = Mangum(app, lifespan="on")
        result = asgi_handler(event, context)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(f"MCP after_mangum elapsed={elapsed_ms}ms status={result.get('statusCode')}", flush=True)
        return result
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(f"MCP handler_error elapsed={elapsed_ms}ms error={type(e).__name__}: {e}", flush=True)
        raise

