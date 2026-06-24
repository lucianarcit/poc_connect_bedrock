"""
Execução local do MCP Server para desenvolvimento e testes.

Uso:
    python -m mcp_server.local

Inicia o servidor em http://localhost:8000/mcp
"""

import uvicorn

from mcp_server.server import mcp_server


def main() -> None:
    """Inicia o MCP Server local com uvicorn."""
    app = mcp_server.streamable_http_app()
    print("=" * 60)
    print("MCP Server fictício — Modo local")
    print("Endpoint: http://localhost:8000/mcp")
    print("Tools: search_support_documentation, get_support_procedure, health_check")
    print("=" * 60)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
