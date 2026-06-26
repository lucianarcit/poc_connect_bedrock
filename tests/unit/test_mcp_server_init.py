"""
Testes de inicialização do MCP Server.

Verifica que o servidor pode ser importado e inicializado sem erros,
o que valida a compatibilidade entre as anotações de tipo e o FastMCP.
"""

import pytest


class TestMCPServerImport:
    """Importação do módulo não deve falhar (issubclass error)."""

    def test_import_mcp_server_module(self):
        """Import do módulo server não deve lançar TypeError."""
        from mcp_server.server import mcp_server
        assert mcp_server is not None

    def test_import_handler(self):
        """Import do handler Lambda (Mangum) deve funcionar."""
        from mcp_server.handler import handler
        assert callable(handler)


class TestMCPServerCreation:
    """Criação do servidor e registro de tools."""

    def test_create_mcp_server_production(self):
        """Factory cria servidor em modo produção sem erro."""
        from mcp_server.server import create_mcp_server
        server = create_mcp_server(environment="production")
        assert server is not None
        assert server.name == "support-mcp-server"

    def test_create_mcp_server_test(self):
        """Factory cria servidor em modo teste sem erro."""
        from mcp_server.server import create_mcp_server
        server = create_mcp_server(environment="test")
        assert server is not None

    def test_tools_registered(self):
        """Todas as 3 tools devem estar registradas."""
        from mcp_server.server import create_mcp_server
        server = create_mcp_server(environment="test")
        tools = server._tool_manager._tools
        tool_names = set(tools.keys())
        assert "search_support_documentation" in tool_names
        assert "get_support_procedure" in tool_names
        assert "health_check" in tool_names
        assert len(tool_names) == 3


class TestToolExecution:
    """Chamada direta de tool via servidor."""

    @pytest.fixture
    def server(self):
        from mcp_server.server import create_mcp_server
        return create_mcp_server(environment="test")

    def test_search_support_documentation(self, server):
        """Tool search_support_documentation pode ser chamada."""
        from mcp_server.tools import search_support_documentation
        from mcp_server.server import get_document_store

        result = search_support_documentation(
            question="como redefinir minha senha",
            product=None,
            language="pt-BR",
            document_store=get_document_store(),
        )
        assert isinstance(result, dict)
        assert "answer" in result or "document_title" in result or "message" in result

    def test_health_check(self, server):
        """Tool health_check retorna status healthy."""
        from mcp_server.tools import health_check
        from mcp_server.server import get_document_store

        result = health_check(document_store=get_document_store())
        assert result["status"] == "healthy"
        assert result["documents_loaded"] > 0
