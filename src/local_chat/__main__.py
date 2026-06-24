"""
Chat local para testar o fluxo MCP sem infraestrutura AWS.

Uso:
    python -m local_chat          (requer MCP Server rodando)
    python -m local_chat --direct (sem servidor HTTP)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Garantir src no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from local_chat.chat_engine import process_message, ChatResponse
from shared.mcp_client.client import MCPClient
from shared.mcp_client.models import ToolResult
from shared.mcp_client.tool_selector import ToolSelector


def _run_loop(call_tool, mode_label: str) -> None:
    """Loop principal do chat."""
    selector = ToolSelector()

    print("=" * 60)
    print(f"Chat Local — {mode_label}")
    print("  Digite 'sair' para encerrar")
    print("=" * 60)
    print()
    print("Bot: Olá! Como posso ajudar você hoje?")
    print()

    while True:
        try:
            user_input = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nBot: Até logo!")
            break

        if not user_input:
            continue

        response = process_message(user_input, call_tool, selector)

        if response.is_exit:
            print(f"\nBot: {response.text}")
            break

        if response.tool_name:
            print(f"  [tool: {response.tool_name}]")

        print(f"\nBot: {response.text}")
        if response.latency_ms > 0:
            print(f"  [latência: {response.latency_ms:.0f}ms]")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat local - POC Amazon Connect + MCP")
    parser.add_argument(
        "--server-url",
        default="http://localhost:8000/mcp",
        help="URL do MCP Server (padrão: http://localhost:8000/mcp)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Modo direto: chama tools sem servidor HTTP",
    )
    args = parser.parse_args()

    if args.direct:
        from mcp_server.documents import DocumentStore
        from mcp_server.tools import (
            get_support_procedure,
            health_check,
            search_support_documentation,
        )

        docs_dir = Path(__file__).resolve().parent.parent.parent / "sample_documents"
        store = DocumentStore.load_from_directory(docs_dir)

        def direct_call(name: str, arguments: dict) -> ToolResult:
            if name == "health_check":
                data = health_check(document_store=store)
            elif name == "get_support_procedure":
                data = get_support_procedure(document_store=store, **arguments)
            else:
                data = search_support_documentation(document_store=store, **arguments)
            return ToolResult(tool_name=name, success=True, data=data, latency_ms=0.0)

        _run_loop(direct_call, "Modo DIRETO (sem servidor HTTP)")
    else:
        client = MCPClient(server_url=args.server_url, timeout_seconds=10.0)
        _run_loop(client.call_tool, f"Servidor MCP: {args.server_url}")


if __name__ == "__main__":
    main()
