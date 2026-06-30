"""
MCP Server fictício de suporte — definição do servidor FastMCP.

Usa o SDK oficial `mcp` com FastMCP em modo stateless HTTP.
As tools são registradas com decoradores @mcp.tool().

NOTA: Este módulo NÃO usa 'from __future__ import annotations' porque o
FastMCP inspeciona as anotações de tipo dos parâmetros com issubclass().
Com annotations postponed (PEP 563), as anotações viram strings e
issubclass() falha com: TypeError: issubclass() arg 1 must be a class.
"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcp_server.documents import DocumentStore

# Determinar diretório dos documentos fictícios
_SAMPLE_DOCS_DIR = os.environ.get(
    "SAMPLE_DOCUMENTS_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "sample_documents"),
)

# Carregar documentos em memória (acontece uma vez no cold start)
_document_store = DocumentStore.load_from_directory(_SAMPLE_DOCS_DIR)


def create_mcp_server(environment: str = "production") -> FastMCP:
    """
    Factory do servidor MCP.

    Args:
        environment: "production" (proteção DNS padrão) ou "test" (hosts de teste permitidos).
    """
    if environment == "test":
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "test",
                "test:80",
                "testserver",
                "testserver:80",
                "localhost",
                "localhost:8000",
                "127.0.0.1",
                "127.0.0.1:8000",
            ],
            allowed_origins=[
                "http://test",
                "http://testserver",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            ],
        )
    else:
        # Produção (Lambda Function URL): desabilitar DNS rebinding protection.
        # A Function URL é protegida por AWS_IAM/SigV4 — apenas callers autorizados
        # conseguem invocar. DNS rebinding não se aplica (não há browser acessando).
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )

    server = FastMCP(
        name="support-mcp-server",
        stateless_http=True,
        json_response=True,
        transport_security=transport_security,
    )
    _register_tools(server)
    return server


def _register_tools(server: FastMCP) -> None:
    """Registra as tools no servidor MCP."""

    @server.tool()
    def search_support_documentation(
        question: str,
        product: str = "",
        language: str = "pt-BR",
    ) -> dict:
        """
        Pesquisa documentos de suporte fictícios por palavras-chave.

        Args:
            question: Pergunta do usuário em linguagem natural.
            product: Nome do produto (opcional). Se vazio, busca em todos.
            language: Idioma preferido (padrão: pt-BR).

        Returns:
            Documento mais relevante encontrado ou mensagem de fallback.
        """
        from mcp_server.tools import search_support_documentation as _search

        return _search(
            question=question,
            product=product or None,
            language=language,
            document_store=_document_store,
        )

    @server.tool()
    def get_support_procedure(procedure_id: str) -> dict:
        """
        Retorna um procedimento de suporte pelo ID (ex: PROC-001).

        Args:
            procedure_id: Identificador do procedimento (formato PROC-XXX).

        Returns:
            Procedimento com título, passos e notas.
        """
        from mcp_server.tools import get_support_procedure as _get_proc

        return _get_proc(procedure_id=procedure_id, document_store=_document_store)

    @server.tool()
    def health_check() -> dict:
        """
        Verifica o status de saúde do servidor MCP.

        Returns:
            Status, versão, quantidade de documentos carregados e timestamp.
        """
        from mcp_server.tools import health_check as _health

        return _health(document_store=_document_store)


# Instância padrão usada APENAS por local_chat e testes ASGI diretos.
# O handler Lambda NÃO usa esta instância — cria uma nova a cada invocação
# via create_mcp_server() para evitar reutilização do StreamableHTTPSessionManager.
mcp_server = create_mcp_server(environment="production")


def get_document_store() -> DocumentStore:
    """Acesso ao store para uso em testes e local_chat."""
    return _document_store
