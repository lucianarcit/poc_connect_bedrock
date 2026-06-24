"""
Processador de mensagem individual do chat.

Responsabilidades:
- Buscar sessão
- Selecionar e chamar tool MCP
- Enviar resposta ao chat
- Renovar token se expirado (uma vez)
- Classificar erros e marcar idempotência
"""

from __future__ import annotations

import logging
import os
from typing import Any

from integrator.exceptions import (
    DynamoDBTransientError,
    ErrorCategory,
    IdempotencyStatus,
)
from integrator.idempotency_repository import IdempotencyRepository
from integrator.models import ConnectChatMessage
from integrator.participant_service import ParticipantService, SendMessageResult
from integrator.session_repository import SessionData, SessionRepository
from shared.crypto import CryptoService, FakeCryptoService, KMSCryptoService
from shared.mcp_client.client import MCPClient
from shared.mcp_client.exceptions import MCPClientError
from shared.mcp_client.models import ToolResult
from shared.mcp_client.tool_selector import ToolSelector

logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = (
    "Desculpe, não consegui processar sua solicitação no momento. "
    "Por favor, tente novamente em alguns instantes."
)


def _is_transient_mcp_error(result: ToolResult) -> bool:
    """Verifica se o erro do MCP é transitório."""
    if result.error is None:
        return False
    transient_indicators = ["timeout", "Timeout", "conectar", "Falha ao conectar", "500", "502", "503", "5xx"]
    return any(ind in result.error for ind in transient_indicators)


class MessageProcessor:
    """Processa uma mensagem de chat individual."""

    def __init__(
        self,
        session_repo: SessionRepository,
        participant_service: ParticipantService,
        crypto: CryptoService,
        mcp_client: MCPClient,
        tool_selector: ToolSelector,
    ) -> None:
        self._sessions = session_repo
        self._participant = participant_service
        self._crypto = crypto
        self._mcp = mcp_client
        self._selector = tool_selector

    @classmethod
    def from_environment(cls, dynamodb_client: Any, cp_client: Any) -> "MessageProcessor":
        """Cria processor a partir de variáveis de ambiente."""
        import boto3

        region = os.environ.get("AWS_REGION", "us-east-1")
        kms_key_id = os.environ.get("KMS_KEY_ID", "")
        mcp_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/mcp")

        if kms_key_id:
            kms_client = boto3.client("kms", region_name=region)
            crypto: CryptoService = KMSCryptoService(kms_client, kms_key_id)
        else:
            crypto = FakeCryptoService()

        return cls(
            session_repo=SessionRepository(
                dynamodb_client=dynamodb_client,
                table_name=os.environ.get("SESSIONS_TABLE_NAME", "connect-mcp-poc-sessions"),
            ),
            participant_service=ParticipantService(connectparticipant_client=cp_client),
            crypto=crypto,
            mcp_client=MCPClient(server_url=mcp_url),
            tool_selector=ToolSelector(),
        )

    def process(self, msg: ConnectChatMessage, idempotency_repo: IdempotencyRepository) -> bool:
        """
        Processa uma mensagem.

        Returns:
            True se o item SQS deve ser marcado como falha (retry).
            False se processado com sucesso (ou FAILED_FINAL sem retry).
        """
        # 1. Buscar sessão
        try:
            session = self._sessions.get_session(msg.contact_id)
        except DynamoDBTransientError:
            return True  # fail item → retry

        if session is None:
            logger.error("Session not found", extra={"contact_id": msg.contact_id})
            idempotency_repo.mark_failed_final(msg.message_id)
            return False

        # 2. Chamar MCP
        tool_name = self._selector.select_tool(msg.content)
        arguments = self._selector.build_arguments(tool_name, msg.content)

        try:
            mcp_result = self._mcp.call_tool(tool_name, arguments)
        except MCPClientError:
            # Erro não encapsulado — transitório
            return True  # fail item → retry

        if not mcp_result.success:
            if _is_transient_mcp_error(mcp_result):
                return True  # fail item → retry
            # Erro FATAL do MCP
            return self._handle_fatal_with_response(
                msg, session, idempotency_repo, GENERIC_ERROR_MESSAGE
            )

        # 3. Formatar resposta
        response_text = self._format_mcp_response(tool_name, mcp_result)

        # 4. Enviar resposta ao chat
        return self._send_response(msg, session, idempotency_repo, response_text)

    def _send_response(
        self,
        msg: ConnectChatMessage,
        session: SessionData,
        idempotency_repo: IdempotencyRepository,
        content: str,
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
            renewed = self._try_renew_and_retry(msg, session, idempotency_repo, content)
            return renewed

        # Erro fatal na entrega
        if send_result.error_category == ErrorCategory.FATAL:
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
    ) -> bool:
        """
        Renova ConnectionToken e retenta SendMessage uma vez.

        Returns:
            True = fail item, False = sucesso ou failed_final.
        """
        # Descriptografar ParticipantToken
        try:
            participant_token = self._crypto.decrypt(session.participant_token_encrypted)
        except Exception:
            idempotency_repo.mark_failed_final(msg.message_id)
            return False

        # Renovar conexão
        renew_result = self._participant.renew_connection(participant_token)

        if not renew_result.success:
            if renew_result.error_category == ErrorCategory.FATAL:
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

        idempotency_repo.mark_failed_final(msg.message_id)
        return False

    def _handle_fatal_with_response(
        self,
        msg: ConnectChatMessage,
        session: SessionData,
        idempotency_repo: IdempotencyRepository,
        content: str,
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
            idempotency_repo.mark_failed_final(msg.message_id)
            return False  # não retry

        if send_result.error_category == ErrorCategory.TRANSIENT:
            # Não perder mensagem — retry entregará a resposta genérica
            return True

        # Fatal no envio também — desistir
        idempotency_repo.mark_failed_final(msg.message_id)
        return False

    @staticmethod
    def _format_mcp_response(tool_name: str, result: ToolResult) -> str:
        """Formata resposta MCP para texto do chat."""
        data = result.data

        if tool_name == "health_check":
            return f"Status: {data.get('status', '?')} | Documentos: {data.get('documents_loaded', 0)}"

        if tool_name == "get_support_procedure":
            title = data.get("title") or "Procedimento"
            steps = data.get("steps", [])
            lines = [title, ""]
            for i, step in enumerate(steps, 1):
                lines.append(f"{i}. {step}")
            return "\n".join(lines)

        # search_support_documentation
        answer = data.get("answer", "Não encontrei informações sobre sua pergunta.")
        doc_title = data.get("document_title")
        if doc_title:
            return f"{doc_title}\n\n{answer}"
        return answer
