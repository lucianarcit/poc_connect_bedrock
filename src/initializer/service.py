"""
Serviço de inicialização do bot CUSTOM_BOT no Amazon Connect.

Orquestra:
1. Extrair ContactId e InstanceId do evento
2. Reservar sessão INITIALIZING no DynamoDB (com lease + ClientTokens)
3. StartContactStreaming
4. CreateParticipant (CUSTOM_BOT)
5. CreateParticipantConnection
6. Criptografar tokens com KMS
7. Atualizar sessão para ACTIVE

Idempotência:
- ClientTokens determinísticos garantem que retries nas APIs Connect são seguros
- Reserva no DynamoDB com lease impede inicialização concorrente
- Sessão ACTIVE com dados completos = já inicializada com sucesso
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from botocore.exceptions import ClientError

from integrator.exceptions import SessionStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InitializationContext:
    """Contexto extraído do evento do Contact Flow."""

    contact_id: str
    instance_id: str
    initial_contact_id: str
    channel: str


def extract_context(event: dict[str, Any]) -> InitializationContext:
    """
    Extrai ContactId, InstanceId e Channel do evento do Contact Flow.

    Raises:
        ValueError: se campos obrigatórios estão ausentes ou canal não é CHAT.
    """
    details = event.get("Details")
    if details is None or not isinstance(details, dict):
        raise ValueError("Evento sem campo 'Details'")

    contact_data = details.get("ContactData")
    if contact_data is None or not isinstance(contact_data, dict):
        raise ValueError("Evento sem campo 'Details.ContactData'")

    contact_id = contact_data.get("ContactId")
    if not contact_id:
        raise ValueError("Evento sem ContactId")

    instance_arn = contact_data.get("InstanceARN", "")
    if not instance_arn:
        raise ValueError("Evento sem InstanceARN")

    # Extrair InstanceId da ARN: arn:aws:connect:region:account:instance/<id>
    try:
        instance_id = instance_arn.split("/")[-1]
        if not instance_id:
            raise ValueError("InstanceId vazio na ARN")
    except (IndexError, AttributeError):
        raise ValueError(f"InstanceARN mal formada: não foi possível extrair InstanceId")

    channel = contact_data.get("Channel", "")
    if channel != "CHAT":
        raise ValueError(f"Canal não suportado: '{channel}'. Apenas CHAT é aceito.")

    initial_contact_id = contact_data.get("InitialContactId", "") or contact_id

    return InitializationContext(
        contact_id=contact_id,
        instance_id=instance_id,
        initial_contact_id=initial_contact_id,
        channel=channel,
    )


def generate_streaming_client_token(instance_id: str, contact_id: str, sns_arn: str) -> str:
    """ClientToken determinístico para StartContactStreaming."""
    payload = f"{instance_id}|{contact_id}|{sns_arn}|streaming"
    return hashlib.sha256(payload.encode()).hexdigest()[:64]


def generate_participant_client_token(instance_id: str, contact_id: str) -> str:
    """ClientToken determinístico para CreateParticipant."""
    payload = f"{instance_id}|{contact_id}|custom-bot-v1"
    return hashlib.sha256(payload.encode()).hexdigest()[:64]


class InitializerService:
    """
    Serviço que orquestra a inicialização do bot.

    Args:
        connect_client: boto3 client para 'connect'
        participant_client: boto3 client para 'connectparticipant'
        kms_client: boto3 client para 'kms'
        dynamodb_client: boto3 client para 'dynamodb'
        sns_topic_arn: ARN do SNS topic para streaming
        kms_key_id: ID da chave KMS para criptografia
        table_name: Nome da tabela DynamoDB de sessões
        lease_seconds: Duração do lease de inicialização
    """

    def __init__(
        self,
        connect_client: Any,
        participant_client: Any,
        kms_client: Any,
        dynamodb_client: Any,
        sns_topic_arn: str,
        kms_key_id: str,
        table_name: str = "connect-mcp-poc-sessions",
        lease_seconds: int = 30,
    ) -> None:
        self._connect = connect_client
        self._participant = participant_client
        self._kms = kms_client
        self._dynamodb = dynamodb_client
        self._sns_topic_arn = sns_topic_arn
        self._kms_key_id = kms_key_id
        self._table_name = table_name
        self._lease_seconds = lease_seconds

    def initialize(self, ctx: InitializationContext) -> dict[str, str]:
        """
        Executa a inicialização completa.

        Returns:
            Dict com status SUCCESS ou ERROR para o Contact Flow.
        """
        try:
            # Verificar se já inicializada
            existing = self._check_existing_session(ctx.contact_id)
            if existing == "ACTIVE_COMPLETE":
                logger.info("Session already active", extra={"contact_id": ctx.contact_id})
                return {"status": "SUCCESS", "botInitialized": "true"}
            elif existing == "INITIALIZING_LEASE_ACTIVE":
                logger.warning("Initialization in progress (lease active)", extra={"contact_id": ctx.contact_id})
                return {"status": "ERROR", "botInitialized": "false", "errorCode": "INITIALIZATION_IN_PROGRESS"}

            # existing == "NOT_FOUND" ou "INITIALIZING_LEASE_EXPIRED"
            # Reservar ou reassumir
            client_tokens = self._reserve_session(ctx)

            # Executar APIs do Connect
            streaming_id = self._start_streaming(ctx, client_tokens["streaming"])
            participant_id, participant_token = self._create_participant(ctx, client_tokens["participant"])
            connection_token, connection_expiry = self._create_connection(participant_token)

            # Criptografar tokens
            participant_token_enc = self._encrypt(participant_token)
            connection_token_enc = self._encrypt(connection_token)

            # Atualizar sessão para ACTIVE
            self._activate_session(
                contact_id=ctx.contact_id,
                participant_id=participant_id,
                participant_token_encrypted=participant_token_enc,
                connection_token_encrypted=connection_token_enc,
                connection_token_expiry=connection_expiry,
                streaming_id=streaming_id,
            )

            logger.info("Initialization complete", extra={"contact_id": ctx.contact_id})
            return {"status": "SUCCESS", "botInitialized": "true"}

        except Exception as e:
            logger.error(
                "Initialization failed",
                extra={"contact_id": ctx.contact_id, "error": str(e)},
            )
            return {"status": "ERROR", "botInitialized": "false", "errorCode": "INITIALIZATION_FAILED"}

    def _check_existing_session(self, contact_id: str) -> str:
        """
        Verifica estado da sessão existente.

        Returns:
            "ACTIVE_COMPLETE" — sessão completa, retornar SUCCESS
            "INITIALIZING_LEASE_ACTIVE" — outra instância inicializando
            "INITIALIZING_LEASE_EXPIRED" — pode reassumir
            "NOT_FOUND" — sessão não existe
        """
        try:
            response = self._dynamodb.get_item(
                TableName=self._table_name,
                Key={"pk": {"S": f"CONTACT#{contact_id}"}},
                ConsistentRead=True,
            )
        except ClientError:
            return "NOT_FOUND"

        item = response.get("Item")
        if item is None:
            return "NOT_FOUND"

        status = item.get("status", {}).get("S", "")

        if status == SessionStatus.ACTIVE.value:
            # Verificar completude
            has_participant = bool(item.get("participant_id", {}).get("S", ""))
            has_token = bool(item.get("connection_token_encrypted", {}).get("B", b""))
            has_expiry = bool(item.get("connection_token_expiry", {}).get("S", ""))
            if has_participant and has_token and has_expiry:
                return "ACTIVE_COMPLETE"

        if status == SessionStatus.INITIALIZING.value:
            lease_expires = int(item.get("initialization_lease_expires_at", {}).get("N", "0"))
            if lease_expires > int(time.time()):
                return "INITIALIZING_LEASE_ACTIVE"
            return "INITIALIZING_LEASE_EXPIRED"

        # Qualquer outro status (ERROR, CLOSED, etc.) — permitir re-inicialização
        return "NOT_FOUND"

    def _reserve_session(self, ctx: InitializationContext) -> dict[str, str]:
        """
        Reserva sessão INITIALIZING com lease no DynamoDB.

        Usa PutItem condicional ou UpdateItem para lease expirado.
        Armazena ClientTokens determinísticos.
        """
        now = int(time.time())
        lease_expires = now + self._lease_seconds
        now_iso = datetime.now(timezone.utc).isoformat()

        streaming_token = generate_streaming_client_token(
            ctx.instance_id, ctx.contact_id, self._sns_topic_arn
        )
        participant_token = generate_participant_client_token(ctx.instance_id, ctx.contact_id)

        try:
            self._dynamodb.put_item(
                TableName=self._table_name,
                Item={
                    "pk": {"S": f"CONTACT#{ctx.contact_id}"},
                    "contact_id": {"S": ctx.contact_id},
                    "participant_id": {"S": ""},
                    "participant_token_encrypted": {"B": b""},
                    "connection_token_encrypted": {"B": b""},
                    "connection_token_expiry": {"S": ""},
                    "streaming_id": {"S": ""},
                    "status": {"S": SessionStatus.INITIALIZING.value},
                    "initialization_lease_expires_at": {"N": str(lease_expires)},
                    "streaming_client_token": {"S": streaming_token},
                    "participant_client_token": {"S": participant_token},
                    "created_at": {"S": now_iso},
                    "updated_at": {"S": now_iso},
                    "expires_at": {"N": str(now + 86400)},
                    "last_message_id": {"S": ""},
                    "handoff_requested": {"BOOL": False},
                },
                ConditionExpression="attribute_not_exists(pk) OR #s = :init",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":init": {"S": SessionStatus.INITIALIZING.value}},
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ConditionalCheckFailedException":
                raise RuntimeError("Session reservation conflict — another instance may be active")
            raise

        return {"streaming": streaming_token, "participant": participant_token}

    def _start_streaming(self, ctx: InitializationContext, client_token: str) -> str:
        """Inicia streaming de mensagens para o SNS."""
        response = self._connect.start_contact_streaming(
            InstanceId=ctx.instance_id,
            ContactId=ctx.contact_id,
            ChatStreamingConfiguration={"StreamingEndpointArn": self._sns_topic_arn},
            ClientToken=client_token,
        )
        return response.get("StreamingId", "")

    def _create_participant(self, ctx: InitializationContext, client_token: str) -> tuple[str, str]:
        """Cria participant CUSTOM_BOT. Retorna (participant_id, participant_token)."""
        response = self._connect.create_participant(
            InstanceId=ctx.instance_id,
            ContactId=ctx.contact_id,
            ParticipantDetails={
                "DisplayName": "Assistente Virtual",
                "ParticipantRole": "CUSTOM_BOT",
            },
            ClientToken=client_token,
        )
        participant_id = response.get("ParticipantId", "")
        credentials = response.get("ParticipantCredentials", {})
        participant_token = credentials.get("ParticipantToken", "")
        return participant_id, participant_token

    def _create_connection(self, participant_token: str) -> tuple[str, str]:
        """Cria conexão do participante. Retorna (connection_token, expiry)."""
        response = self._participant.create_participant_connection(
            ParticipantToken=participant_token,
            Type=["CONNECTION_CREDENTIALS"],
            ConnectParticipant=True,
        )
        creds = response.get("ConnectionCredentials", {})
        connection_token = creds.get("ConnectionToken", "")
        expiry = creds.get("Expiry", "")
        return connection_token, expiry

    def _encrypt(self, plaintext: str) -> bytes:
        """Criptografa um token com KMS."""
        response = self._kms.encrypt(
            KeyId=self._kms_key_id,
            Plaintext=plaintext.encode("utf-8"),
        )
        return response["CiphertextBlob"]

    def _activate_session(
        self,
        contact_id: str,
        participant_id: str,
        participant_token_encrypted: bytes,
        connection_token_encrypted: bytes,
        connection_token_expiry: str,
        streaming_id: str,
    ) -> None:
        """Atualiza sessão de INITIALIZING para ACTIVE com dados completos."""
        now_iso = datetime.now(timezone.utc).isoformat()
        self._dynamodb.update_item(
            TableName=self._table_name,
            Key={"pk": {"S": f"CONTACT#{contact_id}"}},
            UpdateExpression=(
                "SET #status = :status, "
                "participant_id = :pid, "
                "participant_token_encrypted = :pt, "
                "connection_token_encrypted = :ct, "
                "connection_token_expiry = :exp, "
                "streaming_id = :sid, "
                "updated_at = :updated, "
                "initialization_lease_expires_at = :zero"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": {"S": SessionStatus.ACTIVE.value},
                ":pid": {"S": participant_id},
                ":pt": {"B": participant_token_encrypted},
                ":ct": {"B": connection_token_encrypted},
                ":exp": {"S": connection_token_expiry},
                ":sid": {"S": streaming_id},
                ":updated": {"S": now_iso},
                ":zero": {"N": "0"},
            },
            ConditionExpression="attribute_exists(pk)",
        )
