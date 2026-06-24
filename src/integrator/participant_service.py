"""
Cliente do Amazon Connect Participant Service.

Responsabilidades:
- Enviar mensagens ao chat (SendMessage)
- Desconectar participante (DisconnectParticipant)
- Renovar ConnectionToken (CreateParticipantConnection)
- Dividir respostas longas por tamanho UTF-8
- Gerar ClientToken determinístico por (contact_id, source_message_id, chunk_index)
- Classificar erros em categorias estruturadas
- Nunca logar tokens
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from botocore.exceptions import ClientError

from integrator.exceptions import ErrorCategory

logger = logging.getLogger(__name__)

# Limite da API SendMessage: 16.384 bytes UTF-8
# Margem conservadora configurável (padrão: 15.000 bytes)
DEFAULT_MAX_MESSAGE_BYTES = 15_000

# Códigos de erro transitórios (retry)
_TRANSIENT_CODES = {
    "ThrottlingException",
    "InternalServerError",
    "ServiceUnavailable",
    "RequestLimitExceeded",
}


@dataclass(frozen=True)
class SentMessageInfo:
    """Informação de uma mensagem enviada com sucesso."""

    message_id: str
    absolute_time: str


@dataclass(frozen=True)
class SendMessageResult:
    """Resultado do envio de mensagem(ns) ao chat."""

    success: bool
    messages_sent: list[SentMessageInfo] = field(default_factory=list)
    error: str | None = None
    error_category: ErrorCategory | None = None
    failed_chunk_index: int | None = None


@dataclass(frozen=True)
class DisconnectResult:
    """Resultado da desconexão do participante."""

    success: bool
    error: str | None = None
    error_category: ErrorCategory | None = None


@dataclass(frozen=True)
class RenewConnectionResult:
    """Resultado da renovação do ConnectionToken."""

    success: bool
    connection_token: str | None = None
    expiry: str | None = None
    error: str | None = None
    error_category: ErrorCategory | None = None


def generate_client_token(contact_id: str, source_message_id: str, chunk_index: int = 0) -> str:
    """
    Gera ClientToken determinístico para idempotência da API SendMessage.

    Baseado em (contact_id, source_message_id, chunk_index).
    Mesmo input → mesmo token. Mesma resposta para mensagens diferentes → tokens diferentes.
    """
    payload = f"{contact_id}|{source_message_id}|{chunk_index}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


def split_content_by_bytes(content: str, max_bytes: int = DEFAULT_MAX_MESSAGE_BYTES) -> list[str]:
    """
    Divide conteúdo em chunks por tamanho UTF-8 em bytes.

    Tenta cortar em quebra de linha. Se não possível, corta no limite de bytes
    respeitando fronteiras de caractere UTF-8.
    """
    if len(content.encode("utf-8")) <= max_bytes:
        return [content]

    chunks: list[str] = []
    remaining = content

    while remaining:
        encoded = remaining.encode("utf-8")
        if len(encoded) <= max_bytes:
            chunks.append(remaining)
            break

        # Encontrar ponto de corte em bytes
        cut_at = max_bytes

        # Voltar até fronteira de caractere válida
        while cut_at > 0 and (encoded[cut_at] & 0xC0) == 0x80:
            cut_at -= 1

        # Decodificar a porção cortada
        chunk_text = encoded[:cut_at].decode("utf-8")

        # Tentar cortar em quebra de linha (dentro dos últimos 20% do chunk)
        min_cut = int(len(chunk_text) * 0.8)
        newline_pos = chunk_text.rfind("\n", min_cut)
        if newline_pos > 0:
            chunk_text = chunk_text[: newline_pos + 1]

        chunks.append(chunk_text)
        remaining = remaining[len(chunk_text):]

    return chunks


def _classify_error(error: ClientError) -> tuple[str, ErrorCategory]:
    """Classifica um ClientError do ConnectParticipant."""
    code = error.response["Error"]["Code"]
    message = error.response["Error"].get("Message", "")

    if code == "ExpiredTokenException":
        return f"TOKEN_EXPIRED: {message}", ErrorCategory.TRANSIENT

    if code == "AccessDeniedException":
        return f"AUTHORIZATION_ERROR: {message}", ErrorCategory.FATAL

    if code == "ValidationException":
        return f"VALIDATION_ERROR: {message}", ErrorCategory.FATAL

    if code in _TRANSIENT_CODES:
        return f"TRANSIENT [{code}]: {message}", ErrorCategory.TRANSIENT

    # Código desconhecido → tratamento conservador como TRANSIENT
    logger.error("ConnectParticipant unclassified error", extra={"error_code": code})
    return f"UNCLASSIFIED [{code}]: {message}", ErrorCategory.TRANSIENT


class ParticipantService:
    """
    Cliente do Amazon Connect Participant Service.

    Args:
        connectparticipant_client: Cliente boto3 connectparticipant.
        max_message_bytes: Limite de bytes por mensagem (padrão: 15000).
        max_retries: Tentativas para erros transitórios (padrão: 2).
    """

    def __init__(
        self,
        connectparticipant_client: Any,
        max_message_bytes: int = DEFAULT_MAX_MESSAGE_BYTES,
        max_retries: int = 2,
    ) -> None:
        self._client = connectparticipant_client
        self._max_bytes = max_message_bytes
        self._max_retries = max_retries

    def send_message(
        self,
        connection_token: str,
        content: str,
        contact_id: str,
        source_message_id: str,
        content_type: str = "text/plain",
    ) -> SendMessageResult:
        """
        Envia mensagem ao chat. Divide em chunks se necessário.

        ClientTokens são determinísticos por (contact_id, source_message_id, chunk_index).
        Em caso de retry, os mesmos ClientTokens são reutilizados.

        Falha parcial: retorna success=False com messages_sent contendo chunks já enviados
        e failed_chunk_index indicando onde falhou.
        """
        chunks = split_content_by_bytes(content, self._max_bytes)
        sent: list[SentMessageInfo] = []

        for i, chunk in enumerate(chunks):
            client_token = generate_client_token(contact_id, source_message_id, i)
            result = self._send_single(connection_token, chunk, content_type, client_token)

            if not result.success:
                return SendMessageResult(
                    success=False,
                    messages_sent=sent,
                    error=result.error,
                    error_category=result.error_category,
                    failed_chunk_index=i,
                )
            sent.extend(result.messages_sent)

        return SendMessageResult(success=True, messages_sent=sent)

    def _send_single(
        self,
        connection_token: str,
        content: str,
        content_type: str,
        client_token: str,
    ) -> SendMessageResult:
        """Envia uma única mensagem com retry para erros transitórios."""
        last_error: str | None = None
        last_category: ErrorCategory | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.send_message(
                    ConnectionToken=connection_token,
                    Content=content,
                    ContentType=content_type,
                    ClientToken=client_token,
                )
                return SendMessageResult(
                    success=True,
                    messages_sent=[
                        SentMessageInfo(
                            message_id=response.get("Id", ""),
                            absolute_time=response.get("AbsoluteTime", ""),
                        )
                    ],
                )
            except ClientError as e:
                error_msg, category = _classify_error(e)
                last_error = error_msg
                last_category = category

                # Não fazer retry para erros não-transitórios
                if category != ErrorCategory.TRANSIENT:
                    return SendMessageResult(
                        success=False,
                        error=error_msg,
                        error_category=category,
                    )

                # Backoff entre retries transitórios
                if attempt < self._max_retries:
                    time.sleep(0.3 * (2**attempt))

        return SendMessageResult(
            success=False,
            error=last_error,
            error_category=last_category,
        )

    def disconnect_participant(self, connection_token: str) -> DisconnectResult:
        """
        Desconecta o participante do chat.

        Retorna resultado estruturado. O caller decide se continua o handoff.
        """
        try:
            self._client.disconnect_participant(ConnectionToken=connection_token)
            return DisconnectResult(success=True)
        except ClientError as e:
            error_msg, category = _classify_error(e)
            return DisconnectResult(
                success=False,
                error=error_msg,
                error_category=category,
            )

    def renew_connection(self, participant_token: str) -> RenewConnectionResult:
        """
        Renova o ConnectionToken usando o ParticipantToken.

        Retorna novo token (plain text) e expiração.
        O caller deve criptografar antes de persistir.
        """
        last_error: str | None = None
        last_category: ErrorCategory | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.create_participant_connection(
                    ParticipantToken=participant_token,
                    Type=["CONNECTION_CREDENTIALS"],
                    ConnectParticipant=True,
                )
                creds = response.get("ConnectionCredentials", {})
                return RenewConnectionResult(
                    success=True,
                    connection_token=creds.get("ConnectionToken"),
                    expiry=creds.get("Expiry"),
                )
            except ClientError as e:
                error_msg, category = _classify_error(e)
                last_error = error_msg
                last_category = category

                if category != ErrorCategory.TRANSIENT:
                    return RenewConnectionResult(
                        success=False,
                        error=error_msg,
                        error_category=category,
                    )

                if attempt < self._max_retries:
                    time.sleep(0.3 * (2**attempt))

        return RenewConnectionResult(
            success=False,
            error=last_error,
            error_category=last_category,
        )
