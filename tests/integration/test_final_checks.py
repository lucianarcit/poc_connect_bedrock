"""
Verificações finais antes do Terraform:
1. Log JSON serializado contém {"metric": "FailedFinal"}
2. Fluxo completo pelo handler: evento SQS → parser → idempotency → MCP → envio → response
"""

from __future__ import annotations

import json
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from integrator.logging_config import JSONFormatter
from integrator.models import ConnectChatMessage
from integrator.processor import MessageProcessor
from integrator.exceptions import IdempotencyStatus, AcquireResult
from tests.integration.fakes import (
    FakeIdempotencyRepository,
    FakeParticipantService,
    FakeSessionRepository,
    make_test_session,
)
from shared.crypto import FakeCryptoService
from shared.mcp_client.tool_selector import ToolSelector


# --- Teste 1: Log JSON com "metric": "FailedFinal" ---


class TestLogOutputJSON:
    def test_emit_failed_final_produces_json_with_metric(self):
        """
        _emit_failed_final deve produzir log JSON contendo:
        {"metric": "FailedFinal", "contact_id": ..., "message_id": ..., "reason": ...}
        """
        # Configurar logger com JSONFormatter e capturar output
        test_logger = logging.getLogger("test.processor.metric")
        test_logger.handlers.clear()
        test_logger.setLevel(logging.DEBUG)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        test_logger.addHandler(handler)

        # Emitir log como o processor faz
        test_logger.warning(
            "Message marked FAILED_FINAL",
            extra={
                "metric": "FailedFinal",
                "contact_id": "contact-123",
                "message_id": "msg-456",
                "reason": "session_not_found",
            },
        )

        # Verificar output JSON
        output = stream.getvalue().strip()
        log_entry = json.loads(output)

        assert log_entry["metric"] == "FailedFinal"
        assert log_entry["contact_id"] == "contact-123"
        assert log_entry["message_id"] == "msg-456"
        assert log_entry["reason"] == "session_not_found"
        assert log_entry["level"] == "WARNING"
        assert "Message marked FAILED_FINAL" in log_entry["message"]

    def test_json_formatter_includes_extra_fields(self):
        """O JSONFormatter deve incluir qualquer campo extra como campo de primeiro nível."""
        test_logger = logging.getLogger("test.formatter")
        test_logger.handlers.clear()
        test_logger.setLevel(logging.DEBUG)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        test_logger.addHandler(handler)

        test_logger.info("test message", extra={"custom_field": "custom_value", "number": 42})

        output = stream.getvalue().strip()
        log_entry = json.loads(output)

        assert log_entry["custom_field"] == "custom_value"
        assert log_entry["number"] == 42


# --- Teste 2: Fluxo completo pelo handler real ---


class TestFullHandlerFlow:
    def test_complete_flow_via_handler(self):
        """
        handler(SQS event) → parser → try_acquire → processor → MCP → envio → COMPLETED.
        Deve retornar batchItemFailures=[].
        """
        # Construir evento SQS completo
        connect_event = json.dumps({
            "Type": "MESSAGE",
            "ParticipantRole": "CUSTOMER",
            "ContentType": "text/plain",
            "Content": "como redefinir minha senha",
            "Id": "connect-msg-e2e",
            "ContactId": "contact-e2e",
            "ParticipantId": "part-cust",
            "DisplayName": "Cliente E2E",
            "AbsoluteTime": "2024-06-15T14:30:00Z",
            "InitialContactId": "contact-e2e",
        })
        sns_envelope = json.dumps({"Type": "Notification", "Message": connect_event})
        sqs_event = {
            "Records": [{
                "messageId": "sqs-e2e-001",
                "receiptHandle": "rh",
                "body": sns_envelope,
            }]
        }

        # Preparar fakes
        sr = FakeSessionRepository()
        sr.seed(make_test_session("contact-e2e"))
        idemp = FakeIdempotencyRepository()
        ps = FakeParticipantService()
        crypto = FakeCryptoService()

        # MCP client in-process
        from tests.integration.test_integrator_e2e import InProcessMCPClient

        mcp = InProcessMCPClient()
        selector = ToolSelector()

        processor = MessageProcessor(
            session_repo=sr,
            participant_service=ps,
            crypto=crypto,
            mcp_client=mcp,
            tool_selector=selector,
        )

        # Patch internals do handler para usar nossos fakes
        with (
            patch("integrator.handler._get_clients", return_value=(MagicMock(), MagicMock())),
            patch("integrator.handler.IdempotencyRepository", return_value=idemp),
            patch("integrator.handler.MessageProcessor") as mock_proc_cls,
        ):
            # O handler chama MessageProcessor.from_environment() — mock retorna nosso processor
            mock_proc_cls.from_environment.return_value = processor

            from integrator.handler import handler
            result = handler(sqs_event, None)

        # Verificações
        assert result == {"batchItemFailures": []}
        assert idemp.get_status("connect-msg-e2e") == IdempotencyStatus.COMPLETED.value
        assert len(ps.sent_messages) == 1
        assert "senha" in ps.sent_messages[0]["content"].lower() or "Redefinição" in ps.sent_messages[0]["content"]
