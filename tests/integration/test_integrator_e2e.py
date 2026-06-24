"""
Testes de integração local ponta a ponta do Integrator.

Usa:
- MCP Server local real (FastMCP em modo test)
- FakeCryptoService
- FakeSessionRepository
- FakeIdempotencyRepository
- FakeParticipantService
- Processor real
- Sem chamadas boto3 reais
"""

from __future__ import annotations

import json

import pytest

from integrator.exceptions import AcquireResult, ErrorCategory, IdempotencyStatus
from integrator.models import ConnectChatMessage
from integrator.participant_service import RenewConnectionResult, SendMessageResult, SentMessageInfo
from integrator.processor import MessageProcessor
from shared.crypto import FakeCryptoService
from shared.mcp_client.client import MCPClient
from shared.mcp_client.models import ToolResult
from shared.mcp_client.tool_selector import ToolSelector
from tests.integration.fakes import (
    FakeIdempotencyRepository,
    FakeParticipantService,
    FakeSessionRepository,
    make_test_session,
)


# --- Fixture: MCP Client apontando para server real local (via ASGI) ---


class InProcessMCPClient:
    """
    Cliente MCP que chama as tools diretamente (sem HTTP).
    Simula o que o MCPClient faz, mas sem rede.
    """

    def __init__(self):
        from mcp_server.documents import DocumentStore
        from pathlib import Path

        docs_dir = Path(__file__).resolve().parent.parent.parent / "sample_documents"
        self._store = DocumentStore.load_from_directory(docs_dir)

    def call_tool(self, name: str, arguments: dict) -> ToolResult:
        from mcp_server.tools import (
            get_support_procedure,
            health_check,
            search_support_documentation,
        )

        if name == "health_check":
            data = health_check(document_store=self._store)
        elif name == "get_support_procedure":
            data = get_support_procedure(document_store=self._store, **arguments)
        else:
            data = search_support_documentation(document_store=self._store, **arguments)

        return ToolResult(tool_name=name, success=True, data=data, latency_ms=1.0)


class FailingMCPClient:
    """MCP Client que simula falha transitória."""

    def __init__(self, error: str = "Timeout após 10s"):
        self._error = error

    def call_tool(self, name: str, arguments: dict) -> ToolResult:
        return ToolResult(tool_name=name, success=False, error=self._error, latency_ms=100.0)


class FatalMCPClient:
    """MCP Client que simula erro fatal."""

    def call_tool(self, name: str, arguments: dict) -> ToolResult:
        return ToolResult(
            tool_name=name, success=False, error="JSON-RPC error -32601: Method not found"
        )


# --- Helpers ---


def _msg(
    message_id: str = "msg-001",
    contact_id: str = "contact-001",
    content: str = "como redefinir minha senha",
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


def _make_processor(
    mcp_client=None,
    session_repo=None,
    participant_svc=None,
) -> tuple[MessageProcessor, FakeSessionRepository, FakeIdempotencyRepository, FakeParticipantService]:
    sr = session_repo or FakeSessionRepository()
    idemp = FakeIdempotencyRepository()
    ps = participant_svc or FakeParticipantService()
    crypto = FakeCryptoService()
    mcp = mcp_client or InProcessMCPClient()
    selector = ToolSelector()

    if not session_repo:
        sr.seed(make_test_session("contact-001"))

    proc = MessageProcessor(
        session_repo=sr,
        participant_service=ps,
        crypto=crypto,
        mcp_client=mcp,
        tool_selector=selector,
    )
    return proc, sr, idemp, ps


# --- Cenário 1: Pergunta válida → MCP real → resposta → COMPLETED ---


class TestValidQuestionE2E:
    def test_password_reset_question(self):
        """Pergunta sobre senha → MCP retorna DOC-001 → enviado ao chat → COMPLETED."""
        proc, sr, idemp, ps = _make_processor()
        msg = _msg(content="como redefinir minha senha")

        # Handler faria try_acquire antes de chamar process
        acquire = idemp.try_acquire(msg.message_id, msg.contact_id)
        assert acquire == AcquireResult.ACQUIRED

        should_fail = proc.process(msg, idemp)

        assert should_fail is False
        assert idemp.get_status("msg-001") == IdempotencyStatus.COMPLETED.value
        assert len(ps.sent_messages) == 1
        assert "senha" in ps.sent_messages[0]["content"].lower() or "Redefinição" in ps.sent_messages[0]["content"]

    def test_health_check_question(self):
        """Pergunta sobre status → health_check → resposta."""
        proc, sr, idemp, ps = _make_processor()
        msg = _msg(message_id="msg-hc", content="qual o status do sistema")

        idemp.try_acquire(msg.message_id, msg.contact_id)
        should_fail = proc.process(msg, idemp)

        assert should_fail is False
        assert idemp.get_status("msg-hc") == IdempotencyStatus.COMPLETED.value
        assert "healthy" in ps.sent_messages[0]["content"].lower() or "Status" in ps.sent_messages[0]["content"]

    def test_fallback_question(self):
        """Pergunta sem match → fallback → resposta com 'não encontrei'."""
        proc, sr, idemp, ps = _make_processor()
        msg = _msg(message_id="msg-fb", content="qual a previsão do tempo amanhã")

        idemp.try_acquire(msg.message_id, msg.contact_id)
        should_fail = proc.process(msg, idemp)

        assert should_fail is False
        assert idemp.get_status("msg-fb") == IdempotencyStatus.COMPLETED.value
        assert "atendente" in ps.sent_messages[0]["content"].lower() or "não" in ps.sent_messages[0]["content"].lower()


# --- Cenário 2: Duplicata COMPLETED → não envia novamente ---


class TestDuplicateCompleted:
    def test_duplicate_not_sent_again(self):
        """Mensagem já COMPLETED não deve gerar envio."""
        proc, sr, idemp, ps = _make_processor()
        msg = _msg(message_id="msg-dup")

        # Primeira vez
        idemp.try_acquire(msg.message_id, msg.contact_id)
        proc.process(msg, idemp)
        assert len(ps.sent_messages) == 1

        # Segunda vez (duplicata) — handler faria try_acquire e veria DUPLICATE_COMPLETED
        result = idemp.try_acquire("msg-dup", "contact-001")
        assert result == AcquireResult.DUPLICATE_COMPLETED


# --- Cenário 3: MCP transient → batchItemFailures ---


class TestMCPTransientE2E:
    def test_timeout_fails_item(self):
        """MCP timeout → should_fail=True → item fica em batchItemFailures."""
        proc, sr, idemp, ps = _make_processor(mcp_client=FailingMCPClient("Timeout após 10s"))
        msg = _msg(message_id="msg-timeout")

        idemp.try_acquire(msg.message_id, msg.contact_id)
        should_fail = proc.process(msg, idemp)

        assert should_fail is True
        assert len(ps.sent_messages) == 0
        assert idemp.get_status("msg-timeout") == IdempotencyStatus.PROCESSING.value

    def test_connection_error_fails_item(self):
        """MCP connection error → should_fail=True."""
        proc, sr, idemp, ps = _make_processor(mcp_client=FailingMCPClient("Falha ao conectar: refused"))
        msg = _msg(message_id="msg-conn")

        idemp.try_acquire(msg.message_id, msg.contact_id)
        should_fail = proc.process(msg, idemp)

        assert should_fail is True


# --- Cenário 4: MCP fatal + mensagem genérica → FAILED_FINAL ---


class TestMCPFatalE2E:
    def test_fatal_sends_generic_and_marks_failed(self):
        """MCP fatal → envia mensagem genérica → FAILED_FINAL."""
        proc, sr, idemp, ps = _make_processor(mcp_client=FatalMCPClient())
        msg = _msg(message_id="msg-fatal")

        idemp.try_acquire(msg.message_id, msg.contact_id)
        should_fail = proc.process(msg, idemp)

        assert should_fail is False
        assert idemp.get_status("msg-fatal") == IdempotencyStatus.FAILED_FINAL.value
        assert len(ps.sent_messages) == 1
        assert "não consegui" in ps.sent_messages[0]["content"].lower()


# --- Cenário 5: Token expirado → renovação → envio ---


class TestTokenRenewalE2E:
    def test_expired_token_renew_success(self):
        """Token expirado → renova → retenta envio → COMPLETED."""
        ps = FakeParticipantService()
        ps.configure_send(
            SendMessageResult(success=False, error="TOKEN_EXPIRED", error_category=ErrorCategory.TRANSIENT),
            SendMessageResult(success=True, messages_sent=[SentMessageInfo("r2", "T2")]),
        )
        ps.configure_renew(RenewConnectionResult(success=True, connection_token="new-ct", expiry="2099-12-31T00:00:00Z"))

        proc, sr, idemp, _ = _make_processor(participant_svc=ps)
        msg = _msg(message_id="msg-renew")

        idemp.try_acquire(msg.message_id, msg.contact_id)
        should_fail = proc.process(msg, idemp)

        assert should_fail is False
        assert idemp.get_status("msg-renew") == IdempotencyStatus.COMPLETED.value
        assert len(ps.sent_messages) == 2


# --- Cenário 6: Renovação transitória → batchItemFailures ---


class TestRenewalTransientE2E:
    def test_renew_transient_fails_item(self):
        """Renovação falha transitório → should_fail=True."""
        ps = FakeParticipantService()
        ps.configure_send(
            SendMessageResult(success=False, error="TOKEN_EXPIRED", error_category=ErrorCategory.TRANSIENT),
        )
        ps.configure_renew(RenewConnectionResult(
            success=False, error="ThrottlingException", error_category=ErrorCategory.TRANSIENT
        ))

        proc, sr, idemp, _ = _make_processor(participant_svc=ps)
        msg = _msg(message_id="msg-renew-fail")

        idemp.try_acquire(msg.message_id, msg.contact_id)
        should_fail = proc.process(msg, idemp)

        assert should_fail is True
        assert idemp.get_status("msg-renew-fail") == IdempotencyStatus.PROCESSING.value


# --- Cenário 7: Batch misto (1 válido + 1 transitório) ---


class TestMixedBatchE2E:
    def test_one_success_one_transient(self):
        """Batch: msg1 sucesso + msg2 transient → só msg2 em failures."""
        proc_ok, sr, idemp, ps_ok = _make_processor()
        msg1 = _msg(message_id="msg-ok", content="como redefinir minha senha")

        proc_fail, _, _, ps_fail = _make_processor(mcp_client=FailingMCPClient("Timeout"))
        # Reuse same idemp and sr
        sr.seed(make_test_session("contact-001"))

        msg2 = _msg(message_id="msg-fail", content="outra pergunta")

        # Process msg1 OK
        idemp.try_acquire(msg1.message_id, msg1.contact_id)
        fail1 = proc_ok.process(msg1, idemp)
        assert fail1 is False

        # Process msg2 TRANSIENT
        idemp.try_acquire(msg2.message_id, msg2.contact_id)
        fail2 = proc_fail.process(msg2, idemp)
        assert fail2 is True

        # Resultados
        assert idemp.get_status("msg-ok") == IdempotencyStatus.COMPLETED.value
        assert idemp.get_status("msg-fail") == IdempotencyStatus.PROCESSING.value
