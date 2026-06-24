"""Exceções e categorias de erro do Integrator."""

from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    """Classificação estruturada de erros MCP e de processamento."""

    BUSINESS = "BUSINESS"
    """Fallback, documento não encontrado — responde normalmente e conclui."""

    TRANSIENT = "TRANSIENT"
    """Timeout, conexão, HTTP 5xx — falha o registro SQS para retry/DLQ."""

    FATAL = "FATAL"
    """Erro de configuração, JSON-RPC — marca FAILED, não faz retry."""


class EventParsingError(Exception):
    """
    Erro estrutural no parsing do evento SQS/SNS.

    Indica que o body é inválido (JSON malformado, envelope corrompido).
    Deve causar falha do item SQS para retry e eventual DLQ.
    """

    def __init__(self, message: str, sqs_message_id: str) -> None:
        self.sqs_message_id = sqs_message_id
        super().__init__(f"[{sqs_message_id}] {message}")


class IntegratorError(Exception):
    """Erro base do Integrator."""

    def __init__(self, message: str, category: ErrorCategory) -> None:
        self.category = category
        super().__init__(message)
