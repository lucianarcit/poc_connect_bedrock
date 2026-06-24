"""
Motor do chat local — lógica testável sem I/O direto.

Responsabilidades:
- Processar mensagens do usuário
- Selecionar tool MCP
- Formatar respostas
- Detectar handoff
- Detectar encerramento
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from shared.mcp_client.exceptions import MCPClientError
from shared.mcp_client.models import ToolResult
from shared.mcp_client.tool_selector import ToolSelector


# Comandos de handoff (transferência para atendente)
HANDOFF_COMMANDS = [
    "falar com atendente",
    "atendimento humano",
    "quero um atendente",
    "transferir para suporte",
    "transferir",
]

EXIT_COMMANDS = ("sair", "exit", "quit")


@dataclass
class ChatResponse:
    """Resultado do processamento de uma mensagem."""

    text: str
    tool_name: str | None = None
    tool_args: dict | None = None
    latency_ms: float = 0.0
    is_handoff: bool = False
    is_exit: bool = False
    is_error: bool = False


def is_handoff_request(message: str) -> bool:
    """Verifica se o usuário quer ser transferido para atendente."""
    message_lower = message.lower().strip()
    return any(cmd in message_lower for cmd in HANDOFF_COMMANDS)


def is_exit_request(message: str) -> bool:
    """Verifica se o usuário quer encerrar o chat."""
    return message.lower().strip() in EXIT_COMMANDS


def format_response(tool_name: str, data: dict) -> str:
    """Formata a resposta da tool para exibição no chat."""
    if tool_name == "health_check":
        return (
            f"Status: {data.get('status', 'unknown')}\n"
            f"Versao: {data.get('version', '?')}\n"
            f"Documentos carregados: {data.get('documents_loaded', 0)}\n"
            f"Timestamp: {data.get('timestamp', '?')}"
        )

    if tool_name == "get_support_procedure":
        title = data.get("title") or "Procedimento não encontrado"
        steps = data.get("steps", [])
        notes = data.get("notes", [])

        lines = [title]
        if steps:
            lines.append("")
            for i, step in enumerate(steps, 1):
                lines.append(f"{i}. {step}")
        if notes:
            lines.append("")
            lines.append("Observações:")
            for note in notes:
                lines.append(f"- {note}")
        if data.get("demo"):
            lines.append("")
            lines.append("Conteúdo fictício criado exclusivamente para demonstração.")
        return "\n".join(lines)

    # search_support_documentation (padrão)
    answer = data.get("answer", "Sem resposta disponível.")
    doc_title = data.get("document_title")
    doc_id = data.get("document_id")

    lines = []
    if doc_title and doc_id:
        lines.append(f"{doc_title} ({doc_id})")
        lines.append("")
    lines.append(answer)
    if data.get("demo"):
        lines.append("")
        lines.append("Conteúdo fictício criado exclusivamente para demonstração.")
    return "\n".join(lines)


def process_message(
    message: str,
    call_tool: Callable[[str, dict[str, Any]], ToolResult],
    selector: ToolSelector | None = None,
) -> ChatResponse:
    """
    Processa uma mensagem do usuário e retorna a resposta.

    Args:
        message: Texto digitado pelo usuário.
        call_tool: Função que executa a tool MCP (injeção de dependência).
        selector: Seletor de tools (usa padrão se None).

    Returns:
        ChatResponse com texto formatado e metadados.
    """
    if not message.strip():
        return ChatResponse(text="", is_exit=False)

    if is_exit_request(message):
        return ChatResponse(text="Até logo!", is_exit=True)

    if is_handoff_request(message):
        return ChatResponse(
            text="Entendido! Vou transferir você para um atendente humano.",
            is_handoff=True,
        )

    if selector is None:
        selector = ToolSelector()

    tool_name = selector.select_tool(message)
    arguments = selector.build_arguments(tool_name, message)

    try:
        result = call_tool(tool_name, arguments)
    except MCPClientError as e:
        return ChatResponse(
            text="Desculpe, estou com dificuldade para acessar as informações.",
            tool_name=tool_name,
            tool_args=arguments,
            is_error=True,
        )

    if not result.success:
        return ChatResponse(
            text="Desculpe, ocorreu um erro ao buscar a informação.",
            tool_name=tool_name,
            tool_args=arguments,
            latency_ms=result.latency_ms,
            is_error=True,
        )

    formatted = format_response(tool_name, result.data)
    return ChatResponse(
        text=formatted,
        tool_name=tool_name,
        tool_args=arguments,
        latency_ms=result.latency_ms,
    )
