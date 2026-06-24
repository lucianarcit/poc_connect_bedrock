"""
Handler Lambda para o MCP Server.

Usa Mangum para adaptar a aplicação ASGI (FastMCP/Starlette) para o
formato de evento da Lambda Function URL.

Stack: Lambda Function URL → Mangum → Starlette (FastMCP) → JSON-RPC → Tools
"""

from mangum import Mangum

from mcp_server.server import mcp_server

# FastMCP expõe a aplicação ASGI via streamable_http_app()
app = mcp_server.streamable_http_app()

# Mangum adapta ASGI para Lambda handler
# lifespan="off" porque Lambda não suporta lifecycle events ASGI
handler = Mangum(app, lifespan="off")
