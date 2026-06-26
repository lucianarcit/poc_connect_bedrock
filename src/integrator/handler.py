"""
Lambda Integrator handler — processa mensagens do chat via SQS.

Partial batch response: reporta apenas items que falharam.
Formato retornado: {"batchItemFailures": [{"itemIdentifier": "<sqs_message_id>"}]}

Status de idempotência:
- PROCESSING: em processamento (lease ativo)
- COMPLETED: resposta enviada com sucesso
- FAILED_FINAL: erro permanente, resposta genérica enviada (ou impossível de enviar)
- RESPONSE_PENDING: MCP respondeu mas entrega da resposta falhou de forma transitória
"""

from __future__ import annotations

import logging
import os
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

    for result in parsed_results:
        # Erro de parsing → fail item
        if isinstance(result, EventParsingError):
            mid = result.sqs_message_id
            logger.warning("Parsing error", extra={"sqs_message_id": mid, "error": str(result)})
            if mid != "UNKNOWN":
                failures.append({"itemIdentifier": mid})
            continue

        # Skip (evento irrelevante) → sucesso
        if result.chat_message is None:
            logger.info("Skipped event", extra={
                "sqs_message_id": result.sqs_message_id,
                "reason": result.skip_reason,
                "body_length": result.raw_body_length,
            })
            continue

        # Mensagem válida → processar
        msg = result.chat_message
        sqs_id = result.sqs_message_id

        logger.info(
            "Processing message",
            extra={
                "sqs_message_id": sqs_id,
                "message_id": msg.message_id,
                "contact_id": msg.contact_id,
                "participant_role": msg.participant_role,
                "content_type": msg.content_type,
                "content_length": len(msg.content),
            },
        )

        try:
            acquire_result = idempotency_repo.try_acquire(msg.message_id, msg.contact_id)
        except DynamoDBTransientError:
            logger.warning("Idempotency acquire transient error", extra={"message_id": msg.message_id})
            failures.append({"itemIdentifier": sqs_id})
            continue

        if acquire_result == AcquireResult.DUPLICATE_COMPLETED:
            logger.info("Duplicate completed", extra={"message_id": msg.message_id})
            continue

        if acquire_result == AcquireResult.FAILED_FINAL:
            logger.info("Already failed final", extra={"message_id": msg.message_id})
            continue

        if acquire_result == AcquireResult.ALREADY_PROCESSING:
            logger.info("Already processing (lease active)", extra={"message_id": msg.message_id})
            failures.append({"itemIdentifier": sqs_id})
            continue

        # ACQUIRED — processar
        logger.info("Lease acquired, calling processor", extra={"message_id": msg.message_id})
        should_fail = processor.process(msg, idempotency_repo)
        if should_fail:
            logger.warning("Processor returned should_fail=True", extra={"message_id": msg.message_id})
            failures.append({"itemIdentifier": sqs_id})
        else:
            logger.info("Message processed successfully", extra={"message_id": msg.message_id})

    logger.info(
        "Integrator completed",
        extra={"total_records": len(records), "failures": len(failures)},
    )
    return {"batchItemFailures": failures}
