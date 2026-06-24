"""Exceções do cliente MCP."""


class MCPClientError(Exception):
    """Erro base do cliente MCP."""


class MCPConnectionError(MCPClientError):
    """Falha ao conectar com o servidor MCP."""


class MCPTimeoutError(MCPClientError):
    """Timeout na chamada ao servidor MCP."""


class MCPToolNotFoundError(MCPClientError):
    """Tool solicitada não existe no servidor."""


class MCPServerError(MCPClientError):
    """Erro retornado pelo servidor MCP."""
