"""Exceções, enums e categorias de erro do Integrator."""

from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    """Classificação estruturada de erros MCP e de processamento."""

    BUSINESS = "BUSINESS"
    """Fallback, documento não encontrado — responde normalmente e conclui."""

    TRANSIENT = "TRANSIENT"
    """Timeout, conexão, HTTP 5xx — falha o registro SQS para retry/DLQ."""

    FATAL = "FATAL"
    """Erro de configuração, JSON-RPC — marca FAILED_FINAL, não faz retry."""


class SessionStatus(str, Enum):
    """Status de uma sessão de chat."""

    INITIALIZING = "INITIALIZING"
    ACTIVE = "ACTIVE"
    PROCESSING = "PROCESSING"
    HANDOFF_REQUESTED = "HANDOFF_REQUESTED"
    CLOSED = "CLOSED"
    ERROR = "ERROR"


class IdempotencyStatus(str, Enum):
    """Status de um registro de idempotência."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED_FINAL = "FAILED_FINAL"


class AcquireResult(str, Enum):
    """Resultado da tentativa de adquirir lock de processamento."""

    ACQUIRED = "ACQUIRED"
    """Lock adquirido — pode processar a mensagem."""

    DUPLICATE_COMPLETED = "DUPLICATE_COMPLETED"
    """Mensagem já foi processada com sucesso — ignorar."""

    ALREADY_PROCESSING = "ALREADY_PROCESSING"
    """Outra instância está processando (lease ativo) — não processar."""

    FAILED_FINAL = "FAILED_FINAL"
    """Mensagem marcada como falha permanente — não tentar novamente."""


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


class DynamoDBTransientError(IntegratorError):
    """Erro transitório do DynamoDB (throttling, internal error)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorCategory.TRANSIENT)


class DynamoDBFatalError(IntegratorError):
    """Erro fatal do DynamoDB (table not found, validation)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorCategory.FATAL)
