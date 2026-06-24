"""Testes da factory do server e get_document_store."""

from mcp_server.server import create_mcp_server, get_document_store


def test_get_document_store():
    """get_document_store deve retornar store com documentos."""
    store = get_document_store()
    assert store.document_count == 5


def test_create_test_server():
    """Factory com environment=test deve criar server."""
    server = create_mcp_server(environment="test")
    assert server.name == "support-mcp-server"


def test_create_production_server():
    """Factory com environment=production deve criar server."""
    server = create_mcp_server(environment="production")
    assert server.name == "support-mcp-server"
