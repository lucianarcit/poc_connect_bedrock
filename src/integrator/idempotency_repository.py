"""
Repositório de idempotência com lease para controle de duplicidade.

Usa DynamoDB com escritas condicionais para garantir:
- Mensagem nova → ACQUIRED (cria item PROCESSING com lease)
- Mensagem completada → DUPLICATE_COMPLETED (não processa novamente)
- Mensagem em processamento (lease ativo) → ALREADY_PROCESSING
- Mensagem em processamento (lease expirado) → ACQUIRED (reassume)
- Mensagem com falha permanente → FAILED_FINAL (não tenta novamente)
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from integrator.config import get_idempotency_ttl_seconds, get_lease_duration_seconds
from integrator.exceptions import (
    AcquireResult,
    DynamoDBFatalError,
    DynamoDBTransientError,
    IdempotencyStatus,
)

logger = logging.getLogger(__name__)

# Códigos de erro DynamoDB transitórios
_TRANSIENT_ERROR_CODES = {
    "ProvisionedThroughputExceededException",
    "ThrottlingException",
    "InternalServerError",
    "ServiceUnavailable",
    "RequestLimitExceeded",
}

# Códigos de erro DynamoDB fatais
_FATAL_ERROR_CODES = {
    "ResourceNotFoundException",
    "ValidationException",
}


def _classify_dynamo_error(error: ClientError) -> None:
    """
    Classifica e re-levanta erro do DynamoDB.

    Raises:
        DynamoDBTransientError: para erros que justificam retry.
        DynamoDBFatalError: para erros de configuração/validação.
        ClientError: para erros não classificados (tratamento conservador).
    """
    code = error.response["Error"]["Code"]
    message = error.response["Error"].get("Message", "")

    if code in _TRANSIENT_ERROR_CODES:
        raise DynamoDBTransientError(f"DynamoDB transient error [{code}]: {message}")
    if code in _FATAL_ERROR_CODES:
        raise DynamoDBFatalError(f"DynamoDB fatal error [{code}]: {message}")

    # Código desconhecido — log sem dados sensíveis, propagar como ClientError
    logger.error(
        "DynamoDB unclassified error",
        extra={"error_code": code, "error_message": message},
    )
    raise


class IdempotencyRepository:
    """
    Repositório de idempotência com lease-based locking.

    Args:
        dynamodb_client: Cliente boto3 DynamoDB (low-level).
        table_name: Nome da tabela DynamoDB.
        ttl_seconds: TTL dos registros (padrão: 24h).
        lease_duration_seconds: Duração do lease (padrão: 90s).
    """

    def __init__(
        self,
        dynamodb_client: Any,
        table_name: str | None = None,
        ttl_seconds: int | None = None,
        lease_duration_seconds: int | None = None,
    ) -> None:
        self._client = dynamodb_client
        self._table_name = table_name or "connect-mcp-poc-idempotency"
        self._ttl_seconds = ttl_seconds or get_idempotency_ttl_seconds()
        self._lease_duration = lease_duration_seconds or get_lease_duration_seconds()

    def _now_epoch(self) -> int:
        return int(time.time())

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _pk(self, message_id: str) -> str:
        return f"MESSAGE#{message_id}"

    def try_acquire(self, message_id: str, contact_id: str) -> AcquireResult:
        """
        Tenta adquirir lock de processamento para a mensagem.

        Fluxo:
        1. Tenta criar item novo (PutItem condicional)
        2. Se falha (item existe), faz GetItem para inspecionar estado
        3. Decide com base no status e lease
        """
        now = self._now_epoch()
        lease_expires = now + self._lease_duration
        ttl_expires = now + self._ttl_seconds

        # Tentar criar item novo
        try:
            self._client.put_item(
                TableName=self._table_name,
                Item={
                    "pk": {"S": self._pk(message_id)},
                    "contact_id": {"S": contact_id},
                    "status": {"S": IdempotencyStatus.PROCESSING.value},
                    "lease_expires_at": {"N": str(lease_expires)},
                    "attempt_count": {"N": "1"},
                    "updated_at": {"S": self._now_iso()},
                    "expires_at": {"N": str(ttl_expires)},
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
            return AcquireResult.ACQUIRED
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code != "ConditionalCheckFailedException":
                _classify_dynamo_error(e)

        # Item existe — inspecionar estado
        return self._inspect_and_maybe_reassume(message_id, contact_id, now)

    def _inspect_and_maybe_reassume(
        self, message_id: str, contact_id: str, now: int
    ) -> AcquireResult:
        """Inspeciona item existente e decide se pode reassumir."""
        try:
            response = self._client.get_item(
                TableName=self._table_name,
                Key={"pk": {"S": self._pk(message_id)}},
                ConsistentRead=True,
            )
        except ClientError as e:
            _classify_dynamo_error(e)

        item = response.get("Item")
        if item is None:
            # Item foi deletado (TTL) entre PutItem e GetItem — raro, retry é seguro
            return AcquireResult.ACQUIRED

        status = item.get("status", {}).get("S", "")
        lease_expires_at = int(item.get("lease_expires_at", {}).get("N", "0"))
        attempt_count = int(item.get("attempt_count", {}).get("N", "0"))

        # COMPLETED — duplicata confirmada
        if status == IdempotencyStatus.COMPLETED.value:
            return AcquireResult.DUPLICATE_COMPLETED

        # FAILED_FINAL — não tentar novamente
        if status == IdempotencyStatus.FAILED_FINAL.value:
            return AcquireResult.FAILED_FINAL

        # PROCESSING com lease ativo — outra instância processando
        if status == IdempotencyStatus.PROCESSING.value and lease_expires_at > now:
            return AcquireResult.ALREADY_PROCESSING

        # PROCESSING com lease expirado — reassumir
        new_lease = now + self._lease_duration
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={"pk": {"S": self._pk(message_id)}},
                UpdateExpression=(
                    "SET #status = :status, lease_expires_at = :lease, "
                    "attempt_count = :count, updated_at = :updated"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": {"S": IdempotencyStatus.PROCESSING.value},
                    ":lease": {"N": str(new_lease)},
                    ":count": {"N": str(attempt_count + 1)},
                    ":updated": {"S": self._now_iso()},
                    ":old_lease": {"N": str(lease_expires_at)},
                },
                ConditionExpression="lease_expires_at = :old_lease",
            )
            return AcquireResult.ACQUIRED
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ConditionalCheckFailedException":
                # Outra instância reassumiu entre GetItem e UpdateItem
                return AcquireResult.ALREADY_PROCESSING
            _classify_dynamo_error(e)

        # Fallback (não deve chegar aqui)
        return AcquireResult.ALREADY_PROCESSING  # pragma: no cover

    def mark_completed(self, message_id: str) -> None:
        """Marca mensagem como processada com sucesso."""
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={"pk": {"S": self._pk(message_id)}},
                UpdateExpression=(
                    "SET #status = :status, updated_at = :updated"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": {"S": IdempotencyStatus.COMPLETED.value},
                    ":updated": {"S": self._now_iso()},
                },
                ConditionExpression="attribute_exists(pk)",
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ConditionalCheckFailedException":
                logger.warning("mark_completed: item not found", extra={"message_id": message_id})
                return
            _classify_dynamo_error(e)

    def mark_failed_final(self, message_id: str) -> None:
        """Marca mensagem como falha permanente (sem retry)."""
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={"pk": {"S": self._pk(message_id)}},
                UpdateExpression=(
                    "SET #status = :status, updated_at = :updated"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": {"S": IdempotencyStatus.FAILED_FINAL.value},
                    ":updated": {"S": self._now_iso()},
                },
                ConditionExpression="attribute_exists(pk)",
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ConditionalCheckFailedException":
                logger.warning("mark_failed_final: item not found", extra={"message_id": message_id})
                return
            _classify_dynamo_error(e)
