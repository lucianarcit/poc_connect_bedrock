"""
Lambda Integrator handler — processa mensagens do chat via SQS.

Partial batch response: reporta apenas items que falharam.
Formato retornado: {"batchItemFailures": [{"itemIdentifier": "<sqs_message_id>"}]}

Status de idempotência:
- PROCESSING: em processamento (lease ativo)
- COMPLETED: resposta enviada com sucesso
- FAILED_FINAL: erro permanente, resposta genérica enviada (ou impossível de enviar)

Correlation ID:
- Gerado/resolvido ANTES do parsing para que erros de JSON também sejam rastreáveis.
- Ordem de busca configurável: SNS MessageAttributes → payload → UUID v4.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import boto3

from integrator.config import (
    get_idempotency_table_name,
    get_lease_duration_seconds,
    get_sessions_table_name,
)
from integrator.event_parser import parse_sqs_batch
from integrator.exceptions import (
    AcquireResult,
    DynamoDBTransientError,
    ErrorCategory,
    EventParsingError,
)
from integrator.idempotency_repository import IdempotencyRepository
from integrator.logging_config import configure_json_logging
from integrator.processor import MessageProcessor

# Configurar logging JSON no cold start
configure_json_logging()

logger = logging.getLogger(__name__)

# Chaves configuráveis para buscar correlation_id
# Prioridade 1: SNS MessageAttributes
# Prioridade 2: campos no payload do evento
# Prioridade 3: gerar UUID v4
CORRELATION_ID_ATTRIBUTE_KEYS = ("correlation_id", "correlationId", "X-Correlation-Id")
CORRELATION_ID_PAYLOAD_KEYS = ("correlation_id", "correlationId")

_dynamodb_client = None
_cp_client = None


def _get_clients() -> tuple:
    global _dynamodb_client, _cp_client
    region = os.environ.get("AWS_REGION", "us-east-1")
    if _dynamodb_client is None:
        _dynamodb_client = boto3.client("dynamodb", region_name=region)
    if _cp_client is None:
        _cp_client = boto3.client("connectparticipant", region_name=region)
    return _dynamodb_client, _cp_client


def _resolve_correlation_id(record: dict[str, Any]) -> str:
    """Resolve correlation_id do registro SQS ANTES do parse do SNS envelope.

    Ordem de prioridade (chaves configuráveis):
    1. SNS MessageAttributes no wrapper SQS (não requer parse do body)
    2. Campos no payload do evento (requer parse JSON do body — best effort)
    3. Geração local: UUID v4

    Args:
        record: Registro SQS individual.

    Returns:
        Correlation ID resolvido (string não vazia).
    """
    # Prioridade 1: SNS MessageAttributes do record SQS
    message_attributes = record.get("messageAttributes") or {}
    for key in CORRELATION_ID_ATTRIBUTE_KEYS:
        attr = message_attributes.get(key)
        if attr and isinstance(attr, dict):
            value = attr.get("stringValue") or attr.get("Value", "")
            if value and value.strip():
                return value.strip()

    # Prioridade 2: Campos no body (best-effort parse)
    body_raw = record.get("body", "")
    if body_raw:
        try:
            envelope = json.loads(body_raw)
            if isinstance(envelope, dict):
                # Tentar nos MessageAttributes do SNS envelope
                sns_attrs = envelope.get("MessageAttributes") or {}
                for key in CORRELATION_ID_ATTRIBUTE_KEYS:
                    attr = sns_attrs.get(key)
                    if attr and isinstance(attr, dict):
                        value = attr.get("Value", "")
                        if value and value.strip():
                            return value.strip()

                # Tentar no payload do Message
                message_raw = envelope.get("Message", "")
                if message_raw:
                    try:
                        message_data = json.loads(message_raw)
                        if isinstance(message_data, dict):
                            for key in CORRELATION_ID_PAYLOAD_KEYS:
                                value = message_data.get(key, "")
                                if value and str(value).strip():
                                    return str(value).strip()
                    except (json.JSONDecodeError, TypeError):
                        pass
        except (json.JSONDecodeError, TypeError):
            pass

    # Prioridade 3: Gerar UUID v4
    return str(uuid.uuid4())


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler com partial batch response.

    Record sem SQS messageId: falha o batch inteiro (raise).
    """
    records = event.get("Records", [])
    logger.info(
        "Integrator invoked",
        extra={"record_count": len(records)},
    )

    # Validar que todos os records têm messageId
    for i, record in enumerate(records):
        if not record.get("messageId"):
            logger.error(
                "Record without SQS messageId",
                extra={"record_index": i, "body_length": len(record.get("body", ""))},
            )
            raise ValueError(f"Record at index {i} has no SQS messageId — failing entire batch")

    dynamodb, cp_client = _get_clients()

    idempotency_repo = IdempotencyRepository(
        dynamodb_client=dynamodb,
        table_name=get_idempotency_table_name(),
        lease_duration_seconds=get_lease_duration_seconds(),
    )

    processor = MessageProcessor.from_environment(dynamodb, cp_client)

    # Parse batch
    parsed_results = parse_sqs_batch(event)
    failures: list[dict[str, str]] = []

    # Mapear SQS messageId → record para correlação
    records_by_id = {r.get("messageId", ""): r for r in records}

    for result in parsed_results:
        # Resolver correlation_id ANTES de qualquer processamento
        # Para erros de parsing, usar o record original se disponível
        if isinstance(result, EventParsingError):
            mid = result.sqs_message_id
            record = records_by_id.get(mid, {})
            correlation_id = _resolve_correlation_id(record)
            logger.warning(
                "Parsing error",
                extra={"sqs_message_id": mid, "error": str(result), "correlation_id": correlation_id},
            )
            if mid != "UNKNOWN":
                failures.append({"itemIdentifier": mid})
            continue

        # Gerar/resolver correlation_id para este record
        sqs_id = result.sqs_message_id
        record = records_by_id.get(sqs_id, {})
        correlation_id = _resolve_correlation_id(record)

        # Skip (evento irrelevante) → sucesso
        if result.chat_message is None:
            logger.info("Skipped event", extra={
                "sqs_message_id": sqs_id,
                "reason": result.skip_reason,
                "body_length": result.raw_body_length,
                "correlation_id": correlation_id,
            })
            continue

        # Mensagem válida → processar
        msg = result.chat_message

        logger.info(
            "Processing message",
            extra={
                "sqs_message_id": sqs_id,
                "message_id": msg.message_id,
                "contact_id": msg.contact_id,
                "participant_role": msg.participant_role,
                "content_type": msg.content_type,
                "content_length": len(msg.content),
                "correlation_id": correlation_id,
            },
        )

        try:
            acquire_result = idempotency_repo.try_acquire(msg.message_id, msg.contact_id)
        except DynamoDBTransientError:
            logger.warning(
                "Idempotency acquire transient error",
                extra={"message_id": msg.message_id, "correlation_id": correlation_id},
            )
            failures.append({"itemIdentifier": sqs_id})
            continue

        if acquire_result == AcquireResult.DUPLICATE_COMPLETED:
            logger.info("Duplicate completed", extra={"message_id": msg.message_id, "correlation_id": correlation_id})
            continue

        if acquire_result == AcquireResult.FAILED_FINAL:
            logger.info("Already failed final", extra={"message_id": msg.message_id, "correlation_id": correlation_id})
            continue

        if acquire_result == AcquireResult.ALREADY_PROCESSING:
            logger.info(
                "Already processing (lease active)",
                extra={"message_id": msg.message_id, "correlation_id": correlation_id},
            )
            failures.append({"itemIdentifier": sqs_id})
            continue

        # ACQUIRED — processar
        logger.info("Lease acquired, calling processor", extra={
            "message_id": msg.message_id,
            "correlation_id": correlation_id,
        })

        # Obter tempo restante da Lambda para proteção de timeout
        remaining_time_ms: int | None = None
        if context and hasattr(context, "get_remaining_time_in_millis"):
            remaining_time_ms = context.get_remaining_time_in_millis()

        should_fail = processor.process(
            msg,
            idempotency_repo,
            correlation_id=correlation_id,
            remaining_time_ms=remaining_time_ms,
        )
        if should_fail:
            logger.warning(
                "Processor returned should_fail=True",
                extra={"message_id": msg.message_id, "correlation_id": correlation_id},
            )
            failures.append({"itemIdentifier": sqs_id})
        else:
            logger.info(
                "Message processed successfully",
                extra={"message_id": msg.message_id, "correlation_id": correlation_id},
            )

    logger.info(
        "Integrator completed",
        extra={"total_records": len(records), "failures": len(failures)},
    )
    return {"batchItemFailures": failures}
