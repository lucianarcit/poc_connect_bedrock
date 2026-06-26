"""
Parser de eventos SQS → SNS → Amazon Connect Chat.

Responsabilidades:
- Desempacotar o batch SQS
- Extrair envelope SNS do body
- Extrair evento Amazon Connect do campo Message
- Classificar: mensagem relevante, skip, ou erro de parsing
- Retornar ParsedSQSRecord para cada item

Cadeia de desempacotamento:
  SQS Record.body (JSON string)
    → Envelope SNS {Type, Message, MessageAttributes, ...}
      → Message (JSON string)
        → Evento Connect {Id, ContactId, Content, ParticipantRole, Type, ...}
"""

from __future__ import annotations

import json
import logging
from typing import Any

from integrator.exceptions import EventParsingError
from integrator.models import ConnectChatMessage, ParsedSQSRecord

logger = logging.getLogger(__name__)

# Roles que devem ser ignoradas (não são mensagens do cliente)
_IGNORED_ROLES = {"CUSTOM_BOT", "AGENT", "SYSTEM"}

# Content types que representam eventos, não mensagens de texto
_EVENT_CONTENT_TYPES = {
    "application/vnd.amazonaws.connect.event.typing",
    "application/vnd.amazonaws.connect.event.participant.joined",
    "application/vnd.amazonaws.connect.event.participant.left",
    "application/vnd.amazonaws.connect.event.transfer.succeeded",
    "application/vnd.amazonaws.connect.event.transfer.failed",
    "application/vnd.amazonaws.connect.event.chat.ended",
}

# Content types aceitos como mensagens de texto processáveis
_SUPPORTED_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
}


def parse_sqs_batch(event: dict[str, Any]) -> list[ParsedSQSRecord | EventParsingError]:
    """
    Parseia um batch SQS completo.

    Retorna uma lista com ParsedSQSRecord (sucesso ou skip) ou
    EventParsingError (falha estrutural que deve causar retry do item).
    """
    records = event.get("Records", [])
    results: list[ParsedSQSRecord | EventParsingError] = []

    for record in records:
        sqs_message_id = record.get("messageId")
        if not sqs_message_id:
            results.append(
                EventParsingError(
                    message="Record SQS sem messageId",
                    sqs_message_id="UNKNOWN",
                )
            )
            continue

        try:
            parsed = _parse_single_record(record, sqs_message_id)
            results.append(parsed)
        except EventParsingError as e:
            results.append(e)

    return results


def _parse_single_record(record: dict[str, Any], sqs_message_id: str) -> ParsedSQSRecord:
    """
    Parseia um único record SQS.

    Raises:
        EventParsingError: se o body é estruturalmente inválido.
    """
    body_raw = record.get("body", "")
    body_length = len(body_raw.encode("utf-8")) if body_raw else 0

    # Desempacotar envelope SNS
    try:
        sns_envelope = json.loads(body_raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise EventParsingError(
            message=f"Body SQS não é JSON válido: {type(e).__name__}",
            sqs_message_id=sqs_message_id,
        )

    if not isinstance(sns_envelope, dict):
        raise EventParsingError(
            message=f"Body SQS não é um objeto JSON (tipo: {type(sns_envelope).__name__})",
            sqs_message_id=sqs_message_id,
        )

    # Log das chaves presentes no envelope para diagnóstico
    envelope_keys = sorted(sns_envelope.keys())
    sns_type = sns_envelope.get("Type", "")
    logger.info(
        "SNS envelope parsed",
        extra={
            "sqs_message_id": sqs_message_id,
            "envelope_keys": envelope_keys,
            "sns_type": sns_type,
            "has_message_field": "Message" in sns_envelope,
        },
    )

    # Extrair campo Message do envelope SNS
    message_raw = sns_envelope.get("Message")
    if message_raw is None:
        raise EventParsingError(
            message=f"Envelope SNS sem campo 'Message'. Chaves presentes: {envelope_keys}",
            sqs_message_id=sqs_message_id,
        )

    # Desempacotar evento Amazon Connect
    try:
        connect_event = json.loads(message_raw)
    except (json.JSONDecodeError, TypeError) as e:
        raise EventParsingError(
            message=f"Campo 'Message' do SNS não é JSON válido: {type(e).__name__}",
            sqs_message_id=sqs_message_id,
        )

    if not isinstance(connect_event, dict):
        raise EventParsingError(
            message=f"Campo 'Message' não é um objeto JSON (tipo: {type(connect_event).__name__})",
            sqs_message_id=sqs_message_id,
        )

    # Log das chaves do evento Connect para diagnóstico
    connect_keys = sorted(connect_event.keys())
    logger.info(
        "Connect event parsed",
        extra={
            "sqs_message_id": sqs_message_id,
            "connect_event_keys": connect_keys,
            "event_type": connect_event.get("Type", "MISSING"),
            "participant_role": connect_event.get("ParticipantRole", "MISSING"),
            "content_type": connect_event.get("ContentType", "MISSING"),
        },
    )

    # Classificar o evento
    return _classify_connect_event(connect_event, sqs_message_id, body_length)


def _classify_connect_event(
    event: dict[str, Any],
    sqs_message_id: str,
    body_length: int,
) -> ParsedSQSRecord:
    """
    Classifica o evento Connect como relevante (mensagem de cliente) ou skip.
    """
    event_type = event.get("Type", "")
    participant_role = event.get("ParticipantRole", "")
    content_type = event.get("ContentType", "")
    content = event.get("Content", "")
    message_id = event.get("Id", "")
    contact_id = event.get("ContactId", "")

    # Skip: não é mensagem (é evento de sistema)
    if event_type != "MESSAGE":
        return ParsedSQSRecord(
            sqs_message_id=sqs_message_id,
            chat_message=None,
            skip_reason=f"event_type_not_message:{event_type}",
            raw_body_length=body_length,
        )

    # Skip: mensagem do próprio bot, agente ou sistema
    if participant_role in _IGNORED_ROLES:
        return ParsedSQSRecord(
            sqs_message_id=sqs_message_id,
            chat_message=None,
            skip_reason=f"ignored_role:{participant_role}",
            raw_body_length=body_length,
        )

    # Skip: content type é evento (typing, joined, left, etc.)
    if content_type in _EVENT_CONTENT_TYPES:
        return ParsedSQSRecord(
            sqs_message_id=sqs_message_id,
            chat_message=None,
            skip_reason=f"event_content_type:{content_type}",
            raw_body_length=body_length,
        )

    # Skip: content type não é texto suportado
    if content_type not in _SUPPORTED_CONTENT_TYPES:
        return ParsedSQSRecord(
            sqs_message_id=sqs_message_id,
            chat_message=None,
            skip_reason=f"unsupported_content_type:{content_type}",
            raw_body_length=body_length,
        )

    # Skip: conteúdo vazio
    if not content or not content.strip():
        return ParsedSQSRecord(
            sqs_message_id=sqs_message_id,
            chat_message=None,
            skip_reason="empty_content",
            raw_body_length=body_length,
        )

    # Mensagem válida e relevante
    chat_message = ConnectChatMessage(
        message_id=message_id,
        contact_id=contact_id,
        content=content,
        content_type=content_type,
        participant_role=participant_role,
        participant_id=event.get("ParticipantId", ""),
        display_name=event.get("DisplayName", ""),
        absolute_time=event.get("AbsoluteTime", ""),
        initial_contact_id=event.get("InitialContactId", "") or contact_id,
    )

    return ParsedSQSRecord(
        sqs_message_id=sqs_message_id,
        chat_message=chat_message,
        skip_reason=None,
        raw_body_length=body_length,
    )
