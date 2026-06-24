"""Modelos de dados do Integrator — eventos parseados."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectChatMessage:
    """Mensagem de chat do Amazon Connect após parsing completo."""

    message_id: str
    """Id do evento Connect (campo 'Id') — usado para idempotência."""

    contact_id: str
    """ContactId do contato ativo."""

    content: str
    """Texto da mensagem do usuário."""

    content_type: str
    """Tipo do conteúdo (ex: 'text/plain')."""

    participant_role: str
    """Role do participante: CUSTOMER, AGENT, SYSTEM, CUSTOM_BOT."""

    participant_id: str
    """ID do participante que enviou."""

    display_name: str
    """Nome exibido no chat."""

    absolute_time: str
    """Timestamp ISO-8601 do evento."""

    initial_contact_id: str
    """InitialContactId (pode diferir do ContactId em transferências)."""


@dataclass
class ParsedSQSRecord:
    """Resultado do parsing de um record SQS individual."""

    sqs_message_id: str
    """messageId do SQS — usado como itemIdentifier no partial batch response."""

    chat_message: ConnectChatMessage | None
    """Mensagem parseada. None se evento foi classificado como skip."""

    skip_reason: str | None
    """Motivo do skip (se aplicável). None se mensagem é válida e relevante."""

    raw_body_length: int
    """Tamanho do body original em bytes (para diagnóstico, sem conteúdo real)."""
