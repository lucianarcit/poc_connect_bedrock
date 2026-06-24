"""
Repositório de sessões do Amazon Connect no DynamoDB.

Responsabilidades:
- Criar sessões (com ConditionExpression para não sobrescrever)
- Ler sessões
- Atualizar status, tokens, handoff
- Renovar TTL em atualizações relevantes
- Tokens são bytes opacos (criptografados externamente)
- Nunca loga tokens
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from integrator.config import get_session_ttl_seconds
from integrator.exceptions import (
    DynamoDBFatalError,
    DynamoDBTransientError,
    SessionStatus,
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

_FATAL_ERROR_CODES = {
    "ResourceNotFoundException",
    "ValidationException",
}


def _classify_dynamo_error(error: ClientError) -> None:
    """Classifica e re-levanta erro do DynamoDB."""
    code = error.response["Error"]["Code"]
    message = error.response["Error"].get("Message", "")

    if code in _TRANSIENT_ERROR_CODES:
        raise DynamoDBTransientError(f"DynamoDB transient [{code}]: {message}")
    if code in _FATAL_ERROR_CODES:
        raise DynamoDBFatalError(f"DynamoDB fatal [{code}]: {message}")

    logger.error("DynamoDB unclassified error", extra={"error_code": code})
    raise


@dataclass
class SessionData:
    """Dados de uma sessão lidos do DynamoDB."""

    contact_id: str
    participant_id: str
    participant_token_encrypted: bytes
    connection_token_encrypted: bytes
    connection_token_expiry: str
    streaming_id: str
    status: SessionStatus
    created_at: str
    updated_at: str
    expires_at: int
    last_message_id: str
    handoff_requested: bool


class SessionRepository:
    """
    Repositório de sessões para DynamoDB.

    Args:
        dynamodb_client: Cliente boto3 DynamoDB low-level.
        table_name: Nome da tabela.
        ttl_seconds: TTL padrão em segundos.
    """

    def __init__(
        self,
        dynamodb_client: Any,
        table_name: str | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        self._client = dynamodb_client
        self._table_name = table_name or "connect-mcp-poc-sessions"
        self._ttl_seconds = ttl_seconds or get_session_ttl_seconds()

    def _pk(self, contact_id: str) -> str:
        return f"CONTACT#{contact_id}"

    def _now_epoch(self) -> int:
        return int(time.time())

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _new_expires_at(self) -> int:
        return self._now_epoch() + self._ttl_seconds

    def create_session(
        self,
        contact_id: str,
        participant_id: str,
        participant_token_encrypted: bytes,
        connection_token_encrypted: bytes,
        connection_token_expiry: str,
        streaming_id: str,
    ) -> None:
        """
        Cria uma nova sessão.

        Usa ConditionExpression=attribute_not_exists(pk) para não sobrescrever.

        Raises:
            DynamoDBTransientError: em erros transitórios.
            DynamoDBFatalError: em erros de configuração.
            ValueError: se sessão já existe.
        """
        now_iso = self._now_iso()
        try:
            self._client.put_item(
                TableName=self._table_name,
                Item={
                    "pk": {"S": self._pk(contact_id)},
                    "contact_id": {"S": contact_id},
                    "participant_id": {"S": participant_id},
                    "participant_token_encrypted": {"B": participant_token_encrypted},
                    "connection_token_encrypted": {"B": connection_token_encrypted},
                    "connection_token_expiry": {"S": connection_token_expiry},
                    "streaming_id": {"S": streaming_id},
                    "status": {"S": SessionStatus.INITIALIZING.value},
                    "created_at": {"S": now_iso},
                    "updated_at": {"S": now_iso},
                    "expires_at": {"N": str(self._new_expires_at())},
                    "last_message_id": {"S": ""},
                    "handoff_requested": {"BOOL": False},
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ConditionalCheckFailedException":
                raise ValueError(f"Session already exists for contact {contact_id}")
            _classify_dynamo_error(e)

    def get_session(self, contact_id: str) -> SessionData | None:
        """
        Lê uma sessão pelo contact_id.

        Returns:
            SessionData ou None se não existir.
        """
        try:
            response = self._client.get_item(
                TableName=self._table_name,
                Key={"pk": {"S": self._pk(contact_id)}},
                ConsistentRead=True,
            )
        except ClientError as e:
            _classify_dynamo_error(e)

        item = response.get("Item")
        if item is None:
            return None

        return SessionData(
            contact_id=item["contact_id"]["S"],
            participant_id=item["participant_id"]["S"],
            participant_token_encrypted=item["participant_token_encrypted"]["B"],
            connection_token_encrypted=item["connection_token_encrypted"]["B"],
            connection_token_expiry=item["connection_token_expiry"]["S"],
            streaming_id=item["streaming_id"]["S"],
            status=SessionStatus(item["status"]["S"]),
            created_at=item["created_at"]["S"],
            updated_at=item["updated_at"]["S"],
            expires_at=int(item["expires_at"]["N"]),
            last_message_id=item["last_message_id"]["S"],
            handoff_requested=item["handoff_requested"]["BOOL"],
        )

    def update_status(self, contact_id: str, new_status: SessionStatus) -> None:
        """
        Atualiza status da sessão. Renova TTL.

        Raises:
            ValueError: se sessão não existir.
        """
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={"pk": {"S": self._pk(contact_id)}},
                UpdateExpression=(
                    "SET #status = :status, updated_at = :updated, expires_at = :ttl"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": {"S": new_status.value},
                    ":updated": {"S": self._now_iso()},
                    ":ttl": {"N": str(self._new_expires_at())},
                },
                ConditionExpression="attribute_exists(pk)",
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ConditionalCheckFailedException":
                raise ValueError(f"Session not found for contact {contact_id}")
            _classify_dynamo_error(e)

    def update_connection_token(
        self,
        contact_id: str,
        connection_token_encrypted: bytes,
        connection_token_expiry: str,
    ) -> None:
        """
        Atualiza ConnectionToken renovado. Renova TTL.

        Raises:
            ValueError: se sessão não existir.
        """
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={"pk": {"S": self._pk(contact_id)}},
                UpdateExpression=(
                    "SET connection_token_encrypted = :token, "
                    "connection_token_expiry = :expiry, "
                    "updated_at = :updated, expires_at = :ttl"
                ),
                ExpressionAttributeValues={
                    ":token": {"B": connection_token_encrypted},
                    ":expiry": {"S": connection_token_expiry},
                    ":updated": {"S": self._now_iso()},
                    ":ttl": {"N": str(self._new_expires_at())},
                },
                ConditionExpression="attribute_exists(pk)",
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ConditionalCheckFailedException":
                raise ValueError(f"Session not found for contact {contact_id}")
            _classify_dynamo_error(e)

    def mark_handoff(self, contact_id: str) -> None:
        """
        Marca sessão para transferência a atendente humano. Renova TTL.

        Raises:
            ValueError: se sessão não existir.
        """
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key={"pk": {"S": self._pk(contact_id)}},
                UpdateExpression=(
                    "SET #status = :status, handoff_requested = :handoff, "
                    "updated_at = :updated, expires_at = :ttl"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": {"S": SessionStatus.HANDOFF_REQUESTED.value},
                    ":handoff": {"BOOL": True},
                    ":updated": {"S": self._now_iso()},
                    ":ttl": {"N": str(self._new_expires_at())},
                },
                ConditionExpression="attribute_exists(pk)",
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ConditionalCheckFailedException":
                raise ValueError(f"Session not found for contact {contact_id}")
            _classify_dynamo_error(e)
