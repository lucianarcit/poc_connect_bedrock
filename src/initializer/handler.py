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
    request_id = getattr(context, "aws_request_id", "local") if context else "local"

    logger.info(
        "Initializer invoked request_id=%s event_keys=%s",
        request_id,
        sorted(event.keys()) if isinstance(event, dict) else "not_dict",
    )

    try:
        ctx = extract_context(event)
    except ValueError as e:
        logger.error("Initializer invalid_event request_id=%s error=%s", request_id, str(e))
        response = {
            "status": "ERROR",
            "botInitialized": "false",
            "errorCode": "INVALID_EVENT",
        }
        return _validate_string_map(response)

    logger.info(
        "Initializer context contact_id=%s initial_contact_id=%s instance_id=%s request_id=%s",
        ctx.contact_id, ctx.initial_contact_id, ctx.instance_id, request_id,
    )

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
        logger.error(
            "Initializer unhandled_exception contact_id=%s error_type=%s error=%s request_id=%s",
            ctx.contact_id, type(e).__name__, str(e), request_id,
        )
        response = {
            "status": "ERROR",
            "botInitialized": "false",
            "errorCode": "UNHANDLED_EXCEPTION",
        }

    logger.info(
        "Initializer response contact_id=%s status=%s error_code=%s keys=%s value_types=%s request_id=%s",
        ctx.contact_id,
        response.get("status"),
        response.get("errorCode", ""),
        list(response.keys()),
        {k: type(v).__name__ for k, v in response.items()},
        request_id,
    )

    return _validate_string_map(response)


def _validate_string_map(response: object) -> dict[str, str]:
    """Valida que a resposta é STRING_MAP compatível com Amazon Connect."""
    if not isinstance(response, dict):
        raise TypeError(f"Initializer response must be a dict, got {type(response)}")
    if not all(isinstance(k, str) for k in response):
        raise TypeError("Initializer response keys must be strings")
    if not all(isinstance(v, str) for v in response.values()):
        bad = {k: type(v).__name__ for k, v in response.items() if not isinstance(v, str)}
        raise TypeError(f"Initializer response values must be strings, got: {bad}")
    return response
