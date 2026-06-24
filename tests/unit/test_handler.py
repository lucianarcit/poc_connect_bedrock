"""Testes mínimos do handler Lambda."""

from mcp_server.handler import handler


def test_handler_is_callable():
    """O handler Mangum deve ser callable (entry point Lambda)."""
    assert callable(handler)


def test_handler_app_exists():
    """O app ASGI deve existir."""
    from mcp_server.handler import app
    assert app is not None
