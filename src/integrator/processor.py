"""
Processador de mensagem individual do chat.

Responsabilidades:
- Buscar sessão
- Chamar BedrockClient com mensagem do usuário
- Enviar resposta ao chat
- Renovar token se expirado (uma vez)
- Classificar erros e marcar idempotência
- Propagar correlation_id em todos os logs

Segurança de logging:
- NUNCA registrar conteúdo da mensagem ou resposta em NENHUM nível
"""

from __future__ import annotations

import logging
import os
from typing import Any

from integrator.exceptions import (
    DynamoDBTransientError,
    ErrorCategory,
)
from integrator.idempotency_repository import IdempotencyRepository
from integrator.models import ConnectChatMessage
from integrator.participant_service import ParticipantService, SendMessageResult
from integrator.session_repository import SessionData, SessionRepository
from shared.bedrock_client import (
    BedrockClient,
    BedrockFatalError,
    BedrockTimeoutError,
    BedrockTransientError,
)
from shared.crypto import CryptoService, FakeCryptoService, KMSCryptoService

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = (
    "Desculpe, não consegui processar sua solicitação no momento. "
    "Por favor, tente novamente em alguns instantes."
)


class MessageProcessor:
    """Processa uma mensagem de chat individual usando BedrockClient."""

    def __init__(
        self,
        session_repo: SessionRepository,
        participant_service: ParticipantService,
        crypto: CryptoService,
        bedrock_client: BedrockClient,
    ) -> None:
        self._sessions = session_repo
        self._participant = participant_service
        self._crypto = crypto
        self._bedrock = bedrock_client

    @classmethod
    def from_environment(cls, dynamodb_client: Any, cp_client: Any) -> "MessageProcessor":
        """Cria processor a partir de variáveis de ambiente."""
        import boto3

        region = os.environ.get("AWS_REGION", "us-east-1")
        kms_key_id = os.environ.get("KMS_KEY_ID", "")

        if kms_key_id:
            kms_client = boto3.client("kms", region_name=region)
            crypto: CryptoService = KMSCryptoService(kms_client, kms_key_id)
        else:
            crypto = FakeCryptoService()

        # BedrockClient lê suas variáveis de ambiente internamente
        bedrock_client = BedrockClient()

        return cls(
            session_repo=SessionRepository(
                dynamodb_client=dynamodb_client,
                table_name=os.environ.get("SESSIONS_TABLE_NAME", "connect-bedrock-poc-sessions"),
            ),
            participant_service=ParticipantService(connectparticipant_client=cp_client),
            crypto=crypto,
            bedrock_client=bedrock_client,
        )

    def process(
        self,
        msg: ConnectChatMessage,
        idempotency_repo: IdempotencyRepository,
        correlation_id: str | None = None,
        remaining_time_ms: int | None = None,
    ) -> bool:
        """
        Processa uma mensagem.

        Args:
            msg: Mensagem parseada do Amazon Connect.
            idempotency_repo: Repositório de idempotência.
            correlation_id: ID de correlação para rastreamento.
            remaining_time_ms: Tempo restante da Lambda em ms.

        Returns:
            True se o item SQS deve ser marcado como falha (retry).
            False se processado com sucesso (ou FAILED_FINAL sem retry).
        """
        log_extra: dict[str, Any] = {
            "contact_id": msg.contact_id,
            "message_id": msg.message_id,
        }
        if correlation_id:
            log_extra["correlation_id"] = correlation_id

        # 1. Buscar sessão
        try:
            session = self._sessions.get_session(msg.contact_id)
        except DynamoDBTransientError:
            logger.warning("Session lookup transient error", extra=log_extra)
            return True  # fail item → retry

        if session is None:
            logger.error("Session not found", extra=log_extra)
            self._emit_failed_final(msg, reason="session_not_found", correlation_id=correlation_id)
            idempotency_repo.mark_failed_final(msg.message_id)
            return False

        # 2. Chamar BedrockClient
        logger.info(
            "Calling Bedrock Converse API",
            extra={
                **log_extra,
                "model_id": self._bedrock.model_id,
                "content_length": len(msg.content),
            },
        )

        try:
            response_text = self._bedrock.converse(
                user_message=msg.content,
                correlation_id=correlation_id,
                remaining_time_ms=remaining_time_ms,
            )
        except (BedrockTransientError, BedrockTimeoutError):
            # Transitório → fail item para retry via SQS
            logger.warning(
                "Bedrock transient error — failing item for retry",
                extra=log_extra,
            )
            return True
        except BedrockFatalError:
            # Fatal → enviar mensagem genérica ao usuário e marcar FAILED_FINAL
            logger.warning(
                "Bedrock fatal error — sending error message to user",
                extra=log_extra,
            )
            return self._handle_fatal_with_response(
                msg, session, idempotency_repo, GENERIC_ERROR_MESSAGE, correlation_id=correlation_id,
            )

        # 3. Enviar resposta ao chat
        logger.info(
            "Sending response to chat",
            extra={
                **log_extra,
                "response_length": len(response_text),
            },
        )

        return self._send_response(
            msg, session, idempotency_repo, response_text, correlation_id=correlation_id,
        )

    def _send_response(
        self,
        msg: ConnectChatMessage,
        session: SessionData,
        idempotency_repo: IdempotencyRepository,
        content: str,
        correlation_id: str | None = None,
    ) -> bool:
        """
        Envia resposta ao chat. Renova token se expirado (uma vez).

        Returns:
            True = fail item (retry), False = sucesso ou failed_final.
        """
        connection_token = self._crypto.decrypt(session.connection_token_encrypted)

        send_result = self._participant.send_message(
            connection_token=connection_token,
            content=content,
            contact_id=msg.contact_id,
            source_message_id=msg.message_id,
        )

        if send_result.success:
            idempotency_repo.mark_completed(msg.message_id)
            return False  # sucesso

        # Token expirado? Renovar uma vez
        if send_result.error and "TOKEN_EXPIRED" in send_result.error:
            renewed = self._try_renew_and_retry(
                msg, session, idempotency_repo, content, correlation_id=correlation_id,
            )
            return renewed

        # Erro fatal na entrega
        if send_result.error_category == ErrorCategory.FATAL:
            self._emit_failed_final(msg, reason="send_message_fatal", correlation_id=correlation_id)
            idempotency_repo.mark_failed_final(msg.message_id)
            return False

        # Erro transitório na entrega → fail item para retry
        return True

    def _try_renew_and_retry(
        self,
        msg: ConnectChatMessage,
        session: SessionData,
        idempotency_repo: IdempotencyRepository,
        content: str,
        correlation_id: str | None = None,
    ) -> bool:
        """
        Renova ConnectionToken e retenta SendMessage uma vez.

        Returns:
            True = fail item, False = sucesso ou failed_final.
        """
        log_extra: dict[str, Any] = {
            "contact_id": msg.contact_id,
            "message_id": msg.message_id,
        }
        if correlation_id:
            log_extra["correlation_id"] = correlation_id

        # Descriptografar ParticipantToken
        try:
            participant_token = self._crypto.decrypt(session.participant_token_encrypted)
        except Exception:
            self._emit_failed_final(msg, reason="decrypt_participant_token_failed", correlation_id=correlation_id)
            idempotency_repo.mark_failed_final(msg.message_id)
            return False

        # Renovar conexão
        renew_result = self._participant.renew_connection(participant_token)

        if not renew_result.success:
            if renew_result.error_category == ErrorCategory.FATAL:
                self._emit_failed_final(msg, reason="renew_connection_fatal", correlation_id=correlation_id)
                idempotency_repo.mark_failed_final(msg.message_id)
                return False
            # Transitório — fail item
            return True

        # Persistir novo token
        new_token_enc = self._crypto.encrypt(renew_result.connection_token)
        try:
            self._sessions.update_connection_token(
                contact_id=msg.contact_id,
                connection_token_encrypted=new_token_enc,
                connection_token_expiry=renew_result.expiry or "",
            )
        except (DynamoDBTransientError, ValueError):
            return True  # fail item

        # Retentar SendMessage com novo token
        retry_result = self._participant.send_message(
            connection_token=renew_result.connection_token,
            content=content,
            contact_id=msg.contact_id,
            source_message_id=msg.message_id,
        )

        if retry_result.success:
            idempotency_repo.mark_completed(msg.message_id)
            return False

        # Retry falhou — transitório → fail item
        if retry_result.error_category == ErrorCategory.TRANSIENT:
            return True

        self._emit_failed_final(msg, reason="send_after_renew_fatal", correlation_id=correlation_id)
        idempotency_repo.mark_failed_final(msg.message_id)
        return False

    def _handle_fatal_with_response(
        self,
        msg: ConnectChatMessage,
        session: SessionData,
        idempotency_repo: IdempotencyRepository,
        content: str,
        correlation_id: str | None = None,
    ) -> bool:
        """
        Tenta enviar resposta genérica para erro FATAL.

        Se envio funcionar → mark_failed_final, sem retry.
        Se envio falhar transitório → fail item (retry apenas entrega).
        """
        connection_token = self._crypto.decrypt(session.connection_token_encrypted)
        send_result = self._participant.send_message(
            connection_token=connection_token,
            content=content,
            contact_id=msg.contact_id,
            source_message_id=msg.message_id,
        )

        if send_result.success:
            self._emit_failed_final(msg, reason="bedrock_fatal_generic_response_sent", correlation_id=correlation_id)
            idempotency_repo.mark_failed_final(msg.message_id)
            return False  # não retry

        if send_result.error_category == ErrorCategory.TRANSIENT:
            # Não perder mensagem — retry entregará a resposta genérica
            return True

        # Fatal no envio também — desistir
        self._emit_failed_final(msg, reason="bedrock_fatal_generic_response_also_fatal", correlation_id=correlation_id)
        idempotency_repo.mark_failed_final(msg.message_id)
        return False

    def _emit_failed_final(
        self,
        msg: ConnectChatMessage,
        reason: str,
        correlation_id: str | None = None,
    ) -> None:
        """Registra métrica e log estruturado para FAILED_FINAL."""
        extra: dict[str, Any] = {
            "metric": "FailedFinal",
            "contact_id": msg.contact_id,
            "message_id": msg.message_id,
            "reason": reason,
        }
        if correlation_id:
            extra["correlation_id"] = correlation_id
        logger.warning("Message marked FAILED_FINAL", extra=extra)
