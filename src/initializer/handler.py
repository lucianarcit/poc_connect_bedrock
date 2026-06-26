"""
Lambda handler para a Initializer.

Entry point invocado pelo Contact Flow via bloco "Invoke AWS Lambda".
Timeout máximo: 8 segundos (limite do bloco no Contact Flow).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import boto3

from initializer.config import (
    get_initialization_lease_seconds,
    get_kms_key_id,
    get_sessions_table_name,
    get_sns_topic_arn,
)
from initializer.service import InitializerService, extract_context

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Clientes boto3 instanciados fora do handler (reutilizados entre invocações)
_connect_client = None
_participant_client = None
_kms_client = None
_dynamodb_client = None


def _get_clients() -> tuple:
    """Lazy init dos clientes boto3."""
    global _connect_client, _participant_client, _kms_client, _dynamodb_client
    region = os.environ.get("AWS_REGION", "us-east-1")

    if _connect_client is None:
        _connect_client = boto3.client("connect", region_name=region)
    if _participant_client is None:
        _participant_client = boto3.client("connectparticipant", region_name=region)
    if _kms_client is None:
        _kms_client = boto3.client("kms", region_name=region)
    if _dynamodb_client is None:
        _dynamodb_client = boto3.client("dynamodb", region_name=region)

    return _connect_client, _participant_client, _kms_client, _dynamodb_client


def handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    """
    Handler Lambda — inicializa bot CUSTOM_BOT.

    Extrai contexto do evento, delega para InitializerService.
    Retorna dict STRING_MAP compatível com Amazon Connect Contact Flow.
    Todos os valores DEVEM ser strings.
    """
    logger.info(
        "Initializer invoked",
        extra={"event_keys": sorted(event.keys()) if isinstance(event, dict) else "not_dict"},
    )

    try:
        ctx = extract_context(event)
    except ValueError as e:
        logger.error("Invalid event", extra={"error": str(e)})
        response = {
            "status": "ERROR",
            "botInitialized": "false",
            "errorCode": "INVALID_EVENT",
        }
        _log_response(response)
        return response

    connect, participant, kms, dynamodb = _get_clients()

    service = InitializerService(
        connect_client=connect,
        participant_client=participant,
        kms_client=kms,
        dynamodb_client=dynamodb,
        sns_topic_arn=get_sns_topic_arn(),
        kms_key_id=get_kms_key_id(),
        table_name=get_sessions_table_name(),
        lease_seconds=get_initialization_lease_seconds(),
    )

    try:
        response = service.initialize(ctx)
    except Exception as e:
        # Captura qualquer exceção não tratada pelo service.initialize()
        # Garante que o Contact Flow sempre recebe STRING_MAP válido
        logger.error(
            "Unhandled exception in InitializerService",
            extra={"contact_id": ctx.contact_id, "error_type": type(e).__name__, "error": str(e)},
        )
        response = {
            "status": "ERROR",
            "botInitialized": "false",
            "errorCode": "UNHANDLED_EXCEPTION",
        }

    _log_response(response)
    return response


def _log_response(response: dict[str, str]) -> None:
    """Log seguro da resposta retornada ao Contact Flow (sem tokens)."""
    logger.info(
        "Initializer response",
        extra={
            "response_type": type(response).__name__,
            "response_keys": sorted(response.keys()) if isinstance(response, dict) else None,
            "value_types": {k: type(v).__name__ for k, v in response.items()} if isinstance(response, dict) else None,
            "status": response.get("status") if isinstance(response, dict) else None,
        },
    )
