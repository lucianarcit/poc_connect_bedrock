"""Testes mínimos do handler Lambda Integrator (entry point)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from integrator.handler import handler


def _sqs_event(*bodies: str | dict, message_ids: list[str] | None = None) -> dict:
    """Cria evento SQS para o handler."""
    records = []
    for i, body in enumerate(bodies):
        mid = message_ids[i] if message_ids else f"sqs-{i}"
        if isinstance(body, dict):
            body = json.dumps(body)
        records.append({"messageId": mid, "receiptHandle": "rh", "body": body})
    return {"Records": records}


class TestHandlerRecordWithoutMessageId:
    def test_raises_value_error(self):
        """Record sem messageId deve falhar batch inteiro."""
        event = {"Records": [{"body": "{}"}]}
        with pytest.raises(ValueError, match="messageId"):
            handler(event, None)


class TestHandlerSkipEvents:
    @patch("integrator.handler.MessageProcessor")
    @patch("integrator.handler._get_clients")
    def test_irrelevant_events_succeed(self, mock_clients, mock_processor_cls):
        """Eventos irrelevantes (bot message) devem ser sucesso (sem failure)."""
        mock_clients.return_value = (MagicMock(), MagicMock())

        # Evento de bot (ParticipantRole=CUSTOM_BOT)
        connect_event = json.dumps({
            "Type": "MESSAGE",
            "ParticipantRole": "CUSTOM_BOT",
            "ContentType": "text/plain",
            "Content": "bot response",
            "Id": "m1",
            "ContactId": "c1",
            "ParticipantId": "p1",
            "DisplayName": "Bot",
            "AbsoluteTime": "T",
            "InitialContactId": "c1",
        })
        sns_envelope = json.dumps({"Type": "Notification", "Message": connect_event})

        event = _sqs_event(sns_envelope, message_ids=["sqs-1"])
        result = handler(event, None)

        assert result == {"batchItemFailures": []}


class TestHandlerParsingError:
    @patch("integrator.handler.MessageProcessor")
    @patch("integrator.handler._get_clients")
    def test_invalid_json_fails_item(self, mock_clients, mock_processor_cls):
        """JSON inválido deve falhar o item (vai para batchItemFailures)."""
        mock_clients.return_value = (MagicMock(), MagicMock())

        event = _sqs_event("not valid json", message_ids=["sqs-bad"])
        result = handler(event, None)

        assert {"itemIdentifier": "sqs-bad"} in result["batchItemFailures"]


class TestHandlerDuplicateCompleted:
    @patch("integrator.handler.MessageProcessor")
    @patch("integrator.handler._get_clients")
    def test_duplicate_not_in_failures(self, mock_clients, mock_processor_cls):
        """Mensagem duplicada (COMPLETED) não deve aparecer em failures."""
        mock_clients.return_value = (MagicMock(), MagicMock())

        connect_event = json.dumps({
            "Type": "MESSAGE", "ParticipantRole": "CUSTOMER",
            "ContentType": "text/plain", "Content": "hello",
            "Id": "m1", "ContactId": "c1", "ParticipantId": "p1",
            "DisplayName": "User", "AbsoluteTime": "T", "InitialContactId": "c1",
        })
        sns_envelope = json.dumps({"Type": "Notification", "Message": connect_event})
        event = _sqs_event(sns_envelope, message_ids=["sqs-1"])

        # Mock idempotency returns DUPLICATE_COMPLETED
        from integrator.exceptions import AcquireResult
        mock_idemp = MagicMock()
        mock_idemp.try_acquire.return_value = AcquireResult.DUPLICATE_COMPLETED

        with patch("integrator.handler.IdempotencyRepository", return_value=mock_idemp):
            result = handler(event, None)

        assert result == {"batchItemFailures": []}
