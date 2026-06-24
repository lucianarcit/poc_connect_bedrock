"""
Cliente MCP que se comunica com o servidor via Streamable HTTP.

Responsabilidades:
- Enviar requests JSON-RPC ao servidor MCP
- Listar tools disponíveis
- Executar tools
- Controlar timeout e retry
- Registrar latência
- Tratar erros
- Assinar requests com SigV4 quando configurado (Lambda Function URL)

Para a POC, usa httpx para fazer POST direto no endpoint /mcp.
O protocolo MCP Streamable HTTP é baseado em JSON-RPC 2.0.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from shared.mcp_client.exceptions import (
    MCPClientError,
    MCPConnectionError,
    MCPServerError,
    MCPTimeoutError,
    MCPToolNotFoundError,
)
from shared.mcp_client.models import MCPClientProtocol, ToolDefinition, ToolResult
from shared.sigv4 import NoOpSigV4Auth, SigV4Signer


class MCPClient(MCPClientProtocol):
    """
    Cliente MCP via Streamable HTTP (JSON-RPC 2.0).

    Configurável via:
    - server_url: URL do endpoint MCP (ex: http://localhost:8000/mcp)
    - timeout_seconds: timeout por request
    - max_retries: tentativas em caso de falha transitória
    """

    def __init__(
        self,
        server_url: str,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        headers: dict[str, str] | None = None,
        sigv4_auth: SigV4Signer | None = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        }
        self._sigv4 = sigv4_auth or NoOpSigV4Auth()

    def _make_jsonrpc_request(self, method: str, params: dict | None = None) -> dict:
        """Envia um request JSON-RPC 2.0 ao servidor MCP."""
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        body = json.dumps(payload).encode("utf-8")

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                # Assinar headers com SigV4 (no-op se não configurado)
                signed_headers = self._sigv4.sign_headers(
                    method="POST",
                    url=self._server_url,
                    headers=dict(self._base_headers),
                    body=body,
                )

                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(
                        self._server_url,
                        content=body,
                        headers=signed_headers,
                    )

                if response.status_code >= 500:
                    raise MCPServerError(
                        f"Server returned {response.status_code}: {response.text[:200]}"
                    )

                if response.status_code >= 400:
                    raise MCPClientError(
                        f"Client error {response.status_code}: {response.text[:200]}"
                    )

                result = response.json()

                # JSON-RPC error
                if "error" in result:
                    error_data = result["error"]
                    raise MCPServerError(
                        f"JSON-RPC error {error_data.get('code')}: {error_data.get('message')}"
                    )

                return result.get("result", result)

            except httpx.TimeoutException as e:
                last_error = MCPTimeoutError(f"Timeout após {self._timeout}s: {e}")
            except httpx.ConnectError as e:
                last_error = MCPConnectionError(f"Falha ao conectar: {e}")
            except MCPClientError:
                raise
            except Exception as e:
                last_error = MCPClientError(f"Erro inesperado: {e}")

            # Exponential backoff entre retries
            if attempt < self._max_retries:
                time.sleep(0.5 * (2**attempt))

        raise last_error or MCPClientError("Falha após todas as tentativas")

    def list_tools(self) -> list[ToolDefinition]:
        """Lista as tools disponíveis no servidor MCP."""
        result = self._make_jsonrpc_request("tools/list")
        tools_data = result.get("tools", [])
        return [
            ToolDefinition(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """
        Executa uma tool MCP pelo nome.

        Registra a latência da chamada no resultado.
        """
        start = time.time()
        try:
            result = self._make_jsonrpc_request(
                "tools/call",
                {"name": name, "arguments": arguments},
            )
            latency_ms = (time.time() - start) * 1000

            # O resultado vem em result.content[0].text (protocolo MCP)
            content = result.get("content", [])
            if content and isinstance(content, list):
                import json

                first = content[0]
                text = first.get("text", "") if isinstance(first, dict) else str(first)
                try:
                    data = json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    data = {"raw_response": text}
            else:
                data = result if isinstance(result, dict) else {"raw_response": str(result)}

            return ToolResult(
                tool_name=name,
                success=True,
                data=data,
                latency_ms=latency_ms,
            )
        except MCPToolNotFoundError:
            raise
        except MCPClientError as e:
            latency_ms = (time.time() - start) * 1000
            return ToolResult(
                tool_name=name,
                success=False,
                error=str(e),
                latency_ms=latency_ms,
            )
