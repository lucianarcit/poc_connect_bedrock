"""Testes da Lambda Integrator (handler + processor)."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from integrator.exceptions import (
    AcquireResult,
    DynamoDBTransientError,
    ErrorCategory,
    IdempotencyStatus,
    SessionStatus,
)
from integrator.models import ConnectChatMessage
from integrator.participant_service import (
    DisconnectResult,
    RenewConnectionResult,
    SendMessageResult,
    SentMessageInfo,
)
from integrator.processor import MessageProcessor, GENERIC_ERROR_MESSAGE
from integrator.session_repository import SessionData
from shared.crypto import FakeCryptoService
from shared.mcp_client.exceptions import MCPConnectionError
from shared.mcp_client.models import ToolResult
from shared.mcp_client.tool_selector import ToolSelector


# --- Fixtures ---


def _session_data(contact_id="contact-001") -> SessionData:
    crypto = FakeCryptoService()
    return SessionData(
        contact_id=contact_id,
        participant_id="part-001",
        participant_token_encrypted=crypto.encrypt("pt-secret"),
        connection_token_encrypted=crypto.encrypt("ct-secret"),
        connection_token_expiry="2099-01-01T00:00:00Z",
        streaming_id="stream-001",
        status=SessionStatus.ACTIVE,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        expires_at=int(time.time()) + 86400,
        last_message_id="",
        handoff_requested=False,
    )


def _chat_message(
    message_id="msg-001",
    contact_id="contact-001",
    content="como redefinir minha senha",
) -> ConnectChatMessage:
    return ConnectChatMessage(
        message_id=message_id,
        contact_id=contact_id,
        content=content,
        content_type="text/plain",
        participant_role="CUSTOMER",
        participant_id="cust-001",
        display_name="Cliente",
        absolute_time="2024-06-15T14:30:00Z",
        initial_contact_id=contact_id,
    )


@pytest.fixture
def mock_deps():
    """Retorna mocks de todas as dependências do processor."""
    session_repo = MagicMock()
    participant_svc = MagicMock()
    crypto = FakeCryptoService()
    mcp_client = MagicMock()
    selector = ToolSelector()
    idempotency_repo = MagicMock()

    session_repo.get_session.return_value = _session_data()

    return {
        "session_repo": session_repo,
        "participant_svc": participant_svc,
        "crypto": crypto,
        "mcp_client": mcp_client,
        "selector": selector,
        "idempotency_repo": idempotency_repo,
    }


def _make_processor(deps) -> MessageProcessor:
    return MessageProcessor(
        session_repo=deps["session_repo"],
        participant_service=deps["participant_svc"],
        crypto=deps["crypto"],
        mcp_client=deps["mcp_client"],
        tool_selector=deps["selector"],
    )


# --- Tests: Sucesso ---


class TestProcessSuccess:
    def test_full_success(self, mock_deps):
        """Mensagem processada com sucesso: MCP OK → SendMessage OK → mark_completed."""
        mock_deps["mcp_client"].call_tool.return_value = ToolResult(
            tool_name="search_support_documentation",
            success=True,
            data={"answer": "Faça X", "document_title": "DOC", "demo": True},
        )
        mock_deps["participant_svc"].send_message.return_value = SendMessageResult(
            success=True, messages_sent=[SentMessageInfo("r1", "T1")]
        )

        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is False
        mock_deps["idempotency_repo"].mark_completed.assert_called_once_with("msg-001")


# --- Tests: MCP transient ---


class TestMCPTransient:
    def test_mcp_timeout_fails_item(self, mock_deps):
        """Timeout do MCP deve falhar o item para retry via SQS."""
        mock_deps["mcp_client"].call_tool.return_value = ToolResult(
            tool_name="search", success=False, error="Timeout após 10s"
        )
        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is True
        mock_deps["idempotency_repo"].mark_completed.assert_not_called()

    def test_mcp_connection_error_fails_item(self, mock_deps):
        """MCPClientError propagada deve falhar item."""
        mock_deps["mcp_client"].call_tool.side_effect = MCPConnectionError("refused")
        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is True


# --- Tests: MCP fatal ---


class TestMCPFatal:
    def test_mcp_fatal_sends_generic_response(self, mock_deps):
        """Erro fatal MCP deve tentar enviar resposta genérica."""
        mock_deps["mcp_client"].call_tool.return_value = ToolResult(
            tool_name="search", success=False, error="JSON-RPC error -32601: Method not found"
        )
        mock_deps["participant_svc"].send_message.return_value = SendMessageResult(
            success=True, messages_sent=[SentMessageInfo("r1", "T1")]
        )
        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is False
        mock_deps["idempotency_repo"].mark_failed_final.assert_called_once()
        # Verify generic message was sent
        call_args = mock_deps["participant_svc"].send_message.call_args
        assert GENERIC_ERROR_MESSAGE in call_args.kwargs.get("content", call_args[1] if len(call_args[1]) > 1 else "")

    def test_mcp_fatal_generic_response_transient_fail(self, mock_deps):
        """Se envio da resposta genérica falha transitório → fail item (não perder)."""
        mock_deps["mcp_client"].call_tool.return_value = ToolResult(
            tool_name="search", success=False, error="JSON-RPC error"
        )
        mock_deps["participant_svc"].send_message.return_value = SendMessageResult(
            success=False, error="ThrottlingException", error_category=ErrorCategory.TRANSIENT
        )
        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is True  # retry entrega da resposta genérica


# --- Tests: Token expirado e renovação ---


class TestTokenRenewal:
    def test_expired_token_renew_and_retry(self, mock_deps):
        """Token expirado → renova → retenta → sucesso."""
        # Primeiro envio falha com TOKEN_EXPIRED
        mock_deps["mcp_client"].call_tool.return_value = ToolResult(
            tool_name="search", success=True, data={"answer": "ok"}
        )
        mock_deps["participant_svc"].send_message.side_effect = [
            SendMessageResult(success=False, error="TOKEN_EXPIRED", error_category=ErrorCategory.TRANSIENT),
            SendMessageResult(success=True, messages_sent=[SentMessageInfo("r2", "T2")]),
        ]
        mock_deps["participant_svc"].renew_connection.return_value = RenewConnectionResult(
            success=True, connection_token="new-ct", expiry="2099-12-31T00:00:00Z"
        )
        mock_deps["session_repo"].update_connection_token.return_value = None

        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is False
        mock_deps["idempotency_repo"].mark_completed.assert_called_once()
        mock_deps["session_repo"].update_connection_token.assert_called_once()

    def test_renewal_fails_transient(self, mock_deps):
        """Se renovação falha transitório → fail item."""
        mock_deps["mcp_client"].call_tool.return_value = ToolResult(
            tool_name="search", success=True, data={"answer": "ok"}
        )
        mock_deps["participant_svc"].send_message.return_value = SendMessageResult(
            success=False, error="TOKEN_EXPIRED", error_category=ErrorCategory.TRANSIENT
        )
        mock_deps["participant_svc"].renew_connection.return_value = RenewConnectionResult(
            success=False, error="ThrottlingException", error_category=ErrorCategory.TRANSIENT
        )
        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is True

    def test_renewal_fails_fatal(self, mock_deps):
        """Se renovação falha fatal → mark_failed_final, sem retry."""
        mock_deps["mcp_client"].call_tool.return_value = ToolResult(
            tool_name="search", success=True, data={"answer": "ok"}
        )
        mock_deps["participant_svc"].send_message.return_value = SendMessageResult(
            success=False, error="TOKEN_EXPIRED", error_category=ErrorCategory.TRANSIENT
        )
        mock_deps["participant_svc"].renew_connection.return_value = RenewConnectionResult(
            success=False, error="AccessDenied", error_category=ErrorCategory.FATAL
        )
        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is False
        mock_deps["idempotency_repo"].mark_failed_final.assert_called_once()


# --- Tests: Session not found ---


class TestSessionNotFound:
    def test_session_not_found_marks_fatal(self, mock_deps):
        """Sessão inexistente → mark_failed_final."""
        mock_deps["session_repo"].get_session.return_value = None
        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is False
        mock_deps["idempotency_repo"].mark_failed_final.assert_called_once()

    def test_session_dynamo_transient(self, mock_deps):
        """Erro transitório ao buscar sessão → fail item."""
        mock_deps["session_repo"].get_session.side_effect = DynamoDBTransientError("throttle")
        proc = _make_processor(mock_deps)
        should_fail = proc.process(_chat_message(), mock_deps["idempotency_repo"])

        assert should_fail is True


# --- Tests: Partial batch (handler level) ---


class TestHandlerPartialBatch:
    def test_record_without_message_id_fails_batch(self):
        """Record sem messageId deve falhar todo o batch."""
        from integrator.handler import handler
        event = {"Records": [{"body": "{}"}]}
        with pytest.raises(ValueError, match="messageId"):
            handler(event, None)
