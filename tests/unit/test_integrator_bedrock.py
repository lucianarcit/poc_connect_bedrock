"""Testes de integração do Integrator com BedrockClient mockado.

Cobre:
- Fluxo MESSAGE/CUSTOMER completo → Bedrock → SendMessage → COMPLETED
- MESSAGEMETADATA → skip sem Bedrock
- Roles ignoradas → skip
- BedrockTransientError → batchItemFailure
- BedrockFatalError → mensagem de erro + FAILED_FINAL
- Correlation ID propagado em todos os logs
- Partial batch response
- Timeout protection (remaining_time_ms)
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from shared.bedrock_client.exceptions import (
    BedrockFatalError,
    BedrockTimeoutError,
    BedrockTransientError,
)


def _make_sqs_event(messages: list[dict]) -> dict:
    """Helper para criar evento SQS com mensagens Connect."""
    records = []
    for msg in messages:
        sqs_message_id = msg.get("sqs_id", str(uuid.uuid4()))
        connect_event = {
            "Id": msg.get("message_id", str(uuid.uuid4())),
            "ContactId": msg.get("contact_id", "contact-123"),
            "Content": msg.get("content", "Olá, preciso de ajuda"),
            "ContentType": msg.get("content_type", "text/plain"),
            "ParticipantRole": msg.get("participant_role", "CUSTOMER"),
            "Type": msg.get("type", "MESSAGE"),
            "ParticipantId": "participant-abc",
            "DisplayName": "Customer",
            "AbsoluteTime": "2024-01-01T00:00:00Z",
        }
        sns_envelope = {
            "Type": "Notification",
            "Message": json.dumps(connect_event),
            "MessageAttributes": msg.get("message_attributes", {}),
        }
        records.append({
            "messageId": sqs_message_id,
            "body": json.dumps(sns_envelope),
            "messageAttributes": msg.get("sqs_attributes", {}),
        })
    return {"Records": records}


def _make_context(remaining_ms: int = 55000) -> MagicMock:
    """Helper para criar Lambda context mock."""
    ctx = MagicMock()
    ctx.get_remaining_time_in_millis.return_value = remaining_ms
    return ctx


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch):
    """Configuração de ambiente para todos os testes."""
    monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
    monkeypatch.setenv("BEDROCK_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("SESSIONS_TABLE_NAME", "test-sessions")
    monkeypatch.setenv("IDEMPOTENCY_TABLE_NAME", "test-idempotency")
    monkeypatch.setenv("KMS_KEY_ID", "")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("LEASE_DURATION_SECONDS", "90")


@pytest.fixture
def mock_deps():
    """Mock das dependências externas."""
    with patch("integrator.handler.boto3.client") as mock_boto3, \
         patch("integrator.processor.BedrockClient") as mock_bedrock_cls, \
         patch("integrator.handler.IdempotencyRepository") as mock_idemp_cls, \
         patch("integrator.processor.SessionRepository") as mock_session_cls, \
         patch("integrator.processor.ParticipantService") as mock_ps_cls, \
         patch("integrator.processor.KMSCryptoService") as mock_kms_crypto, \
         patch("integrator.processor.FakeCryptoService") as mock_fake_crypto_cls:

        # Configurar mock do BedrockClient
        mock_bedrock = MagicMock()
        mock_bedrock.model_id = "test-model"
        mock_bedrock.converse.return_value = "Resposta do Bedrock em português"
        mock_bedrock_cls.return_value = mock_bedrock

        # Configurar mock do IdempotencyRepository
        mock_idemp = MagicMock()
        mock_idemp.try_acquire.return_value = "ACQUIRED"
        mock_idemp_cls.return_value = mock_idemp

        # Configurar mock da SessionRepository
        mock_session = MagicMock()
        session_data = MagicMock()
        session_data.connection_token_encrypted = b"ENC:fake-connection-token"
        session_data.participant_token_encrypted = b"ENC:fake-participant-token"
        mock_session.get_session.return_value = session_data
        mock_session_cls.return_value = mock_session

        # Configurar mock do CryptoService (FakeCryptoService é usado quando KMS_KEY_ID="")
        mock_crypto = MagicMock()
        mock_crypto.decrypt.return_value = "decrypted-connection-token"
        mock_crypto.encrypt.return_value = b"ENC:new-token"
        mock_fake_crypto_cls.return_value = mock_crypto

        # Configurar mock do ParticipantService
        mock_ps = MagicMock()
        send_result = MagicMock()
        send_result.success = True
        send_result.error = None
        send_result.error_category = None
        mock_ps.send_message.return_value = send_result
        mock_ps_cls.return_value = mock_ps

        yield {
            "boto3": mock_boto3,
            "bedrock": mock_bedrock,
            "bedrock_cls": mock_bedrock_cls,
            "idempotency": mock_idemp,
            "session_repo": mock_session,
            "participant_service": mock_ps,
            "session_data": session_data,
            "crypto": mock_crypto,
        }


class TestMessageCustomerFlow:
    """Fluxo completo: MESSAGE/CUSTOMER → Bedrock → SendMessage → COMPLETED."""

    def test_successful_flow(self, mock_deps):
        from integrator.handler import handler

        event = _make_sqs_event([{"content": "Qual é a capital?"}])
        context = _make_context()

        result = handler(event, context)

        assert result["batchItemFailures"] == []
        mock_deps["bedrock"].converse.assert_called_once()
        mock_deps["participant_service"].send_message.assert_called_once()
        mock_deps["idempotency"].mark_completed.assert_called_once()

    def test_bedrock_receives_message_content(self, mock_deps):
        from integrator.handler import handler

        event = _make_sqs_event([{"content": "Minha pergunta"}])
        context = _make_context()

        handler(event, context)

        call_kwargs = mock_deps["bedrock"].converse.call_args[1]
        assert call_kwargs["user_message"] == "Minha pergunta"

    def test_remaining_time_ms_passed_to_bedrock(self, mock_deps):
        from integrator.handler import handler

        event = _make_sqs_event([{"content": "Pergunta"}])
        context = _make_context(remaining_ms=45000)

        handler(event, context)

        call_kwargs = mock_deps["bedrock"].converse.call_args[1]
        assert call_kwargs["remaining_time_ms"] == 45000


class TestMessageMetadataSkip:
    """Eventos MESSAGEMETADATA são ignorados silenciosamente."""

    def test_messagemetadata_skip(self, mock_deps):
        from integrator.handler import handler

        event = _make_sqs_event([{"type": "EVENT", "content": ""}])
        context = _make_context()

        result = handler(event, context)

        assert result["batchItemFailures"] == []
        mock_deps["bedrock"].converse.assert_not_called()

    def test_event_type_not_message_skip(self, mock_deps):
        from integrator.handler import handler

        event = _make_sqs_event([{"type": "MESSAGEMETADATA", "content": ""}])
        context = _make_context()

        result = handler(event, context)

        assert result["batchItemFailures"] == []
        mock_deps["bedrock"].converse.assert_not_called()


class TestRoleFiltering:
    """Roles não-CUSTOMER são ignoradas."""

    @pytest.mark.parametrize("role", ["CUSTOM_BOT", "AGENT", "SYSTEM"])
    def test_ignored_roles(self, mock_deps, role):
        from integrator.handler import handler

        event = _make_sqs_event([{"participant_role": role}])
        context = _make_context()

        result = handler(event, context)

        assert result["batchItemFailures"] == []
        mock_deps["bedrock"].converse.assert_not_called()

    def test_customer_role_processed(self, mock_deps):
        from integrator.handler import handler

        event = _make_sqs_event([{"participant_role": "CUSTOMER"}])
        context = _make_context()

        handler(event, context)

        mock_deps["bedrock"].converse.assert_called_once()


class TestContentTypeFiltering:
    """Apenas text/plain e text/markdown são processados."""

    @pytest.mark.parametrize("ct", ["text/plain", "text/markdown"])
    def test_supported_content_types(self, mock_deps, ct):
        from integrator.handler import handler

        event = _make_sqs_event([{"content_type": ct}])
        context = _make_context()

        handler(event, context)

        mock_deps["bedrock"].converse.assert_called_once()

    def test_unsupported_content_type_skip(self, mock_deps):
        from integrator.handler import handler

        event = _make_sqs_event([{"content_type": "application/json"}])
        context = _make_context()

        result = handler(event, context)

        assert result["batchItemFailures"] == []
        mock_deps["bedrock"].converse.assert_not_called()


class TestBedrockErrors:
    """Tratamento de erros do Bedrock."""

    def test_transient_error_fails_item(self, mock_deps):
        from integrator.handler import handler

        mock_deps["bedrock"].converse.side_effect = BedrockTransientError(
            "throttled", error_code="ThrottlingException"
        )
        event = _make_sqs_event([{"sqs_id": "msg-1"}])
        context = _make_context()

        result = handler(event, context)

        assert result["batchItemFailures"] == [{"itemIdentifier": "msg-1"}]
        mock_deps["idempotency"].mark_completed.assert_not_called()
        mock_deps["idempotency"].mark_failed_final.assert_not_called()

    def test_timeout_error_fails_item(self, mock_deps):
        from integrator.handler import handler

        mock_deps["bedrock"].converse.side_effect = BedrockTimeoutError(
            "timeout", error_code="ReadTimeoutError"
        )
        event = _make_sqs_event([{"sqs_id": "msg-2"}])
        context = _make_context()

        result = handler(event, context)

        assert result["batchItemFailures"] == [{"itemIdentifier": "msg-2"}]

    def test_fatal_error_sends_message_and_marks_failed_final(self, mock_deps):
        from integrator.handler import handler

        mock_deps["bedrock"].converse.side_effect = BedrockFatalError(
            "access denied", error_code="AccessDeniedException"
        )
        event = _make_sqs_event([{"sqs_id": "msg-3"}])
        context = _make_context()

        result = handler(event, context)

        # Não falha o item (não retry)
        assert result["batchItemFailures"] == []
        # Envia mensagem genérica ao usuário
        mock_deps["participant_service"].send_message.assert_called_once()
        # Marca FAILED_FINAL
        mock_deps["idempotency"].mark_failed_final.assert_called_once()


class TestPartialBatchResponse:
    """Partial batch response com mix de sucesso e falha."""

    def test_mixed_batch(self, mock_deps):
        from integrator.handler import handler

        # Configurar: primeira chamada sucesso, segunda throttle
        mock_deps["bedrock"].converse.side_effect = [
            "Resposta OK",
            BedrockTransientError("throttled", error_code="ThrottlingException"),
        ]

        event = _make_sqs_event([
            {"sqs_id": "success-1", "message_id": "m1", "content": "P1"},
            {"sqs_id": "fail-1", "message_id": "m2", "content": "P2"},
        ])
        context = _make_context()

        result = handler(event, context)

        # Apenas o segundo falhou
        assert result["batchItemFailures"] == [{"itemIdentifier": "fail-1"}]


class TestCorrelationId:
    """Correlation ID gerado antes do parsing e propagado."""

    def test_correlation_id_generated_when_not_in_attributes(self, mock_deps, caplog):
        from integrator.handler import handler
        import logging

        event = _make_sqs_event([{"content": "teste"}])
        context = _make_context()

        with caplog.at_level(logging.INFO):
            handler(event, context)

        # Verificar que correlation_id está presente nos logs
        processing_records = [r for r in caplog.records if "Processing message" in r.getMessage()]
        assert len(processing_records) >= 1
        assert hasattr(processing_records[0], "correlation_id")
        assert processing_records[0].correlation_id  # não é vazio

    def test_correlation_id_from_sqs_attributes(self, mock_deps, caplog):
        from integrator.handler import handler
        import logging

        event = _make_sqs_event([{
            "content": "teste",
            "sqs_attributes": {
                "correlation_id": {
                    "stringValue": "my-custom-corr-id",
                    "dataType": "String",
                }
            },
        }])
        context = _make_context()

        with caplog.at_level(logging.INFO):
            handler(event, context)

        processing_records = [r for r in caplog.records if "Processing message" in r.getMessage()]
        assert len(processing_records) >= 1
        assert processing_records[0].correlation_id == "my-custom-corr-id"

    def test_correlation_id_passed_to_bedrock(self, mock_deps):
        from integrator.handler import handler

        event = _make_sqs_event([{
            "content": "teste",
            "sqs_attributes": {
                "correlation_id": {
                    "stringValue": "bedrock-corr-123",
                    "dataType": "String",
                }
            },
        }])
        context = _make_context()

        handler(event, context)

        call_kwargs = mock_deps["bedrock"].converse.call_args[1]
        assert call_kwargs["correlation_id"] == "bedrock-corr-123"

    def test_correlation_id_present_on_parse_error(self, mock_deps, caplog):
        from integrator.handler import handler
        import logging

        # Body inválido (não-JSON) → parsing error com correlation_id
        records = [{
            "messageId": "bad-msg",
            "body": "not-json-{{{",
            "messageAttributes": {},
        }]
        event = {"Records": records}
        context = _make_context()

        with caplog.at_level(logging.WARNING):
            result = handler(event, context)

        assert result["batchItemFailures"] == [{"itemIdentifier": "bad-msg"}]
        # Correlation ID presente mesmo em erros de parsing
        parsing_records = [r for r in caplog.records if "Parsing error" in r.getMessage()]
        assert len(parsing_records) >= 1
        assert hasattr(parsing_records[0], "correlation_id")
        assert parsing_records[0].correlation_id  # UUID v4 gerado
