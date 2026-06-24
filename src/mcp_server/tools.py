"""
Definição das tools MCP do servidor de suporte fictício.

Tools disponíveis:
- search_support_documentation: busca documentos por pergunta
- get_support_procedure: retorna procedimento passo-a-passo
- health_check: status do servidor
"""

from __future__ import annotations

from datetime import datetime, timezone


def search_support_documentation(
    question: str,
    product: str | None = None,
    language: str = "pt-BR",
    *,
    document_store,
) -> dict:
    """
    Pesquisa documentos de suporte fictícios.

    Busca o documento mais relevante usando palavras-chave.
    Retorna fallback quando não encontra resultado.
    """
    doc = document_store.search(question, product)

    if doc is None:
        return {
            "answer": (
                "Não encontrei informações específicas sobre sua pergunta. "
                "Posso transferir você para um atendente humano se desejar. "
                "Digite 'falar com atendente' para ser transferido."
            ),
            "document_id": None,
            "document_title": None,
            "reference": None,
            "confidence": 0.0,
            "demo": True,
        }

    return {
        "answer": doc.content,
        "document_id": doc.id,
        "document_title": doc.title,
        "reference": f"Fonte: {doc.title} ({doc.id})",
        "confidence": 0.95,
        "demo": True,
    }


def get_support_procedure(
    procedure_id: str,
    *,
    document_store,
) -> dict:
    """
    Retorna um procedimento de suporte pelo ID.

    Usado quando o usuário solicita passos específicos.
    """
    proc = document_store.get_procedure(procedure_id)

    if proc is None:
        return {
            "procedure_id": procedure_id,
            "title": None,
            "steps": [],
            "notes": ["Procedimento não encontrado."],
            "source": None,
            "demo": True,
        }

    return {
        "procedure_id": proc.procedure_id,
        "title": proc.title,
        "steps": proc.steps,
        "notes": proc.notes,
        "source": proc.source,
        "demo": True,
    }


def health_check(*, document_store) -> dict:
    """
    Retorna o status de saúde do servidor MCP.
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "documents_loaded": document_store.document_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
