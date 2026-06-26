"""
Cliente MCP que se comunica com o servidor via Streamable HTTP.

Responsabilidades:
- Enviar requests JSON-RPC ao servidor MCP
- Gerenciar sessão MCP (initialize → notifications/initialized → tools/call)
- Controlar timeout e retry
- Registrar latência
- Tratar erros
- Assinar requests com SigV4 quando configurado (Lambda Function URL)

Protocolo MCP Streamable HTTP:
1. POST /mcp com initialize → 200 JSON (capturar Mcp-Session-Id)
2. POST /mcp com notifications/initialized → 202 Accepted (corpo vazio)
3. POST /mcp com tools/call → 200 JSON com resultado

O cliente gerencia a sessão por invocação Lambda (stateless entre invocações).
"""

from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)


class MCPClient(MCPClientProtocol):
    """
    Cliente MCP via Streamable HTTP (JSON-RPC 2.0).

    Gerencia sessão MCP: initialize → initialized → tools/call.
    """

    def __init__(
        self,
        server_url: str,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        headers: dict[str, str] | None = None,
        sigv4_auth: SigV4Signer | None = None,
    ) -> None:
        self._server_url = server_url
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **(headers or {}),
        }
        self._sigv4 = sigv4_auth or NoOpSigV4Auth()
        self._session_id: str | None = None
        self._initialized = False
        logger.info("MCPClient created server_url=%r", self._server_url)

    def _post(self, payload: dict, is_notification: bool = False) -> httpx.Response:
        """
        Envia POST ao endpoint MCP com SigV4 e session headers.

        Redirect handling controlado:
        - Se receber 307/308, segue o Location UMA vez com nova assinatura SigV4
        - Rejeita redirect para host diferente
        - Se segundo request também for 3xx, reporta redirect loop
        """
        body = json.dumps(payload).encode("utf-8")
        response = self._signed_post(self._server_url, body)

        # Tratar redirect (uma vez)
        if 300 <= response.status_code < 400:
            redirect_url = self._resolve_redirect(response, self._server_url)
            logger.info(
                "MCP redirect original_url=%r redirect_url=%r status=%d",
                self._server_url, redirect_url, response.status_code,
            )
            # Segunda tentativa com nova assinatura
            response = self._signed_post(redirect_url, body)
            if 300 <= response.status_code < 400:
                second_location = response.headers.get("location", "")
                raise MCPClientError(
                    f"Redirect loop detected: {response.status_code} → '{second_location}'. "
                    f"Original: '{self._server_url}', first redirect: '{redirect_url}'."
                )

        # Capturar session ID se retornado
        session_header = response.headers.get("mcp-session-id")
        if session_header:
            self._session_id = session_header

        return response

    def _signed_post(self, url: str, body: bytes) -> httpx.Response:
        """Executa POST assinado com SigV4 para a URL especificada."""
        headers = dict(self._base_headers)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        signed_headers = self._sigv4.sign_headers(
            method="POST",
            url=url,
            headers=headers,
            body=body,
        )

        logger.info("MCP signed_post url=%r", url)

        with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
            response = client.post(url, content=body, headers=signed_headers)

        logger.info(
            "MCP signed_post response status=%d content_length=%d",
            response.status_code, len(response.content),
        )
        return response

    def _resolve_redirect(self, response: httpx.Response, original_url: str) -> str:
        """
        Resolve Location do redirect. Valida same-origin.

        Raises:
            MCPClientError: se Location ausente ou host diferente.
        """
        from urllib.parse import urlparse, urljoin

        location = response.headers.get("location", "")
        if not location:
            raise MCPClientError(
                f"Redirect {response.status_code} without Location header"
            )

        # Resolver URL relativa
        resolved = urljoin(original_url, location)

        # Validar same-origin (scheme + host)
        orig_parsed = urlparse(original_url)
        redir_parsed = urlparse(resolved)

        if orig_parsed.scheme != redir_parsed.scheme or orig_parsed.netloc != redir_parsed.netloc:
            raise MCPClientError(
                f"Redirect to different host rejected: '{resolved}' "
                f"(original: '{original_url}')"
            )

        return resolved

        # Capturar session ID se retornado
        session_header = response.headers.get("mcp-session-id")
        if session_header:
            self._session_id = session_header

        return response

    def _ensure_initialized(self) -> None:
        """Garante que a sessão MCP está inicializada."""
        if self._initialized:
            return

        # 1. initialize
        init_payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "connect-mcp-integrator", "version": "1.0"},
            },
        }

        response = self._post(init_payload)

        if response.status_code >= 400:
            raise MCPServerError(f"MCP initialize failed: {response.status_code}")

        # Parse initialize response (pode ser JSON ou SSE)
        self._parse_init_response(response)

        # 2. notifications/initialized
        notif_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }

        notif_response = self._post(notif_payload, is_notification=True)
        # 202 Accepted com corpo vazio é esperado para notifications
        logger.info(
            "MCP session initialized",
            extra={
                "session_id": self._session_id or "none",
                "init_status": response.status_code,
                "notif_status": notif_response.status_code,
            },
        )

        self._initialized = True

    def _parse_init_response(self, response: httpx.Response) -> None:
        """Parse da resposta initialize (JSON ou SSE)."""
        content_type = response.headers.get("content-type", "")

        if "application/json" in content_type:
            # JSON direto
            if response.text.strip():
                data = response.json()
                if "error" in data:
                    raise MCPServerError(f"MCP init error: {data['error']}")
        elif "text/event-stream" in content_type:
            # SSE — extrair dados JSON dos events
            for line in response.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if "error" in data:
                            raise MCPServerError(f"MCP init error: {data['error']}")
                    except json.JSONDecodeError:
                        pass
        # 200 com corpo vazio ou 202 — ok, sessão criada

    def _make_jsonrpc_request(self, method: str, params: dict | None = None) -> dict:
        """Envia um request JSON-RPC 2.0 ao servidor MCP."""
        self._ensure_initialized()

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._post(payload)

                logger.info(
                    "MCP HTTP response",
                    extra={
                        "method": method,
                        "status_code": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                        "content_length": len(response.content),
                    },
                )

                if response.status_code >= 500:
                    raise MCPServerError(
                        f"Server returned {response.status_code}: {response.text[:200]}"
                    )

                if response.status_code >= 400:
                    raise MCPClientError(
                        f"Client error {response.status_code}: {response.text[:200]}"
                    )

                # Parse response based on Content-Type
                result = self._parse_response(response)

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
            except MCPServerError:
                raise
            except Exception as e:
                last_error = MCPClientError(f"Erro inesperado: {e}")

            if attempt < self._max_retries:
                time.sleep(0.5 * (2**attempt))

        raise last_error or MCPClientError("Falha após todas as tentativas")

    def _parse_response(self, response: httpx.Response) -> dict:
        """Parse da resposta MCP: JSON ou SSE."""
        content_type = response.headers.get("content-type", "")

        if not response.text.strip():
            raise MCPClientError(
                f"Empty response body (status={response.status_code}, content-type={content_type})"
            )

        if "application/json" in content_type:
            return response.json()

        if "text/event-stream" in content_type:
            # SSE: extrair último data event com JSON-RPC result
            last_data = None
            for line in response.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        last_data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        pass
            if last_data:
                return last_data
            raise MCPClientError(f"SSE response without parseable data events")

        # Tentar parse como JSON independente do content-type
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError):
            raise MCPClientError(
                f"Unparseable response (status={response.status_code}, "
                f"content-type={content_type}, length={len(response.content)})"
            )

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
