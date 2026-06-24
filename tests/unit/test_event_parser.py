"""Testes do parser de eventos SQS/SNS/Amazon Connect."""

from __future__ import annotations

import json

import pytest

from integrator.event_parser import parse_sqs_batch
from integrator.exceptions import EventParsingError
from integrator.models import ConnectChatMessage, ParsedSQSRecord


# --- Helpers para construir fixtures ---


def _connect_event(
    content: str = "Como redefinir minha senha?",
    content_type: str = "text/plain",
    participant_role: str = "CUSTOMER",
    event_type: str = "MESSAGE",
    message_id: str = "connect-msg-001",
    contact_id: str = "contact-001",
    participant_id: str = "participant-001",
    display_name: str = "Cliente",
    absolute_time: str = "2024-06-15T14:30:00.000Z",
    initial_contact_id: str | None = None,
) -> dict:
    """Cria um evento Amazon Connect Chat."""
    return {
        "AbsoluteTime": absolute_time,
        "Content": content,
        "ContentType": content_type,
        "Id": message_id,
        "Type": event_type,
        "ParticipantId": participant_id,
        "DisplayName": display_name,
        "ParticipantRole": participant_role,
        "InitialContactId": initial_contact_id or contact_id,
        "ContactId": contact_id,
    }


def _sns_envelope(connect_event: dict) -> dict:
    """Empacota evento Connect em envelope SNS."""
    return {
        "Type": "Notification",
        "MessageId": "sns-msg-001",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:topic",
        "Message": json.dumps(connect_event),
        "MessageAttributes": {
            "Type": {"Type": "String", "Value": connect_event.get("Type", "MESSAGE")},
            "ParticipantRole": {"Type": "String", "Value": connect_event.get("ParticipantRole", "CUSTOMER")},
            "ContactId": {"Type": "String", "Value": connect_event.get("ContactId", "contact-001")},
            "ContentType": {"Type": "String", "Value": connect_event.get("ContentType", "text/plain")},
        },
    }


def _sqs_record(
    body: str | dict,
    sqs_message_id: str = "sqs-msg-001",
) -> dict:
    """Cria um record SQS."""
    if isinstance(body, dict):
        body = json.dumps(body)
    return {
        "messageId": sqs_message_id,
        "receiptHandle": "fake-receipt-handle",
        "body": body,
        "attributes": {"ApproximateReceiveCount": "1"},
        "eventSource": "aws:sqs",
    }


def _sqs_event(*records: dict) -> dict:
    """Cria um evento SQS com múltiplos records."""
    return {"Records": list(records)}


def _valid_sqs_record(
    sqs_message_id: str = "sqs-msg-001",
    content: str = "Como redefinir minha senha?",
    **connect_kwargs,
) -> dict:
    """Cria um record SQS completo e válido."""
    ce = _connect_event(content=content, **connect_kwargs)
    envelope = _sns_envelope(ce)
    return _sqs_record(body=envelope, sqs_message_id=sqs_message_id)


# --- Testes de parsing bem-sucedido ---


class TestParseSuccess:
    def test_customer_message(self):
        """Mensagem CUSTOMER com text/plain deve retornar ConnectChatMessage."""
        event = _sqs_event(_valid_sqs_record())
        results = parse_sqs_batch(event)

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, ParsedSQSRecord)
        assert result.chat_message is not None
        assert result.skip_reason is None
        assert result.sqs_message_id == "sqs-msg-001"

    def test_fields_extracted_correctly(self):
        """Todos os campos devem ser extraídos corretamente."""
        event = _sqs_event(_valid_sqs_record(
            content="teste",
            message_id="msg-123",
            contact_id="contact-456",
            participant_id="part-789",
            display_name="João",
            absolute_time="2024-01-01T00:00:00Z",
            initial_contact_id="initial-456",
        ))
        results = parse_sqs_batch(event)
        msg = results[0].chat_message

        assert msg.message_id == "msg-123"
        assert msg.contact_id == "contact-456"
        assert msg.content == "teste"
        assert msg.content_type == "text/plain"
        assert msg.participant_role == "CUSTOMER"
        assert msg.participant_id == "part-789"
        assert msg.display_name == "João"
        assert msg.absolute_time == "2024-01-01T00:00:00Z"
        assert msg.initial_contact_id == "initial-456"

    def test_initial_contact_id_fallback(self):
        """Se InitialContactId ausente, deve usar ContactId."""
        ce = _connect_event(contact_id="contact-abc")
        ce.pop("InitialContactId")
        envelope = _sns_envelope(ce)
        record = _sqs_record(body=envelope)
        results = parse_sqs_batch(_sqs_event(record))

        msg = results[0].chat_message
        assert msg.initial_contact_id == "contact-abc"

    def test_batch_multiple_records(self):
        """Batch com 3 records: 1 válido, 1 bot (skip), 1 válido."""
        r1 = _valid_sqs_record(sqs_message_id="sqs-1", content="pergunta 1")
        r2 = _valid_sqs_record(sqs_message_id="sqs-2", participant_role="CUSTOM_BOT")
        r3 = _valid_sqs_record(sqs_message_id="sqs-3", content="pergunta 2")
        results = parse_sqs_batch(_sqs_event(r1, r2, r3))

        assert len(results) == 3
        assert results[0].chat_message is not None
        assert results[1].skip_reason is not None
        assert results[2].chat_message is not None

    def test_raw_body_length(self):
        """raw_body_length deve conter o tamanho em bytes do body."""
        record = _valid_sqs_record()
        results = parse_sqs_batch(_sqs_event(record))
        assert results[0].raw_body_length > 0


# --- Testes de skip (evento irrelevante, sem retry) ---


class TestSkipEvents:
    def test_skip_custom_bot(self):
        """Mensagem do CUSTOM_BOT deve ser ignorada."""
        record = _valid_sqs_record(participant_role="CUSTOM_BOT")
        results = parse_sqs_batch(_sqs_event(record))

        assert results[0].chat_message is None
        assert "ignored_role:CUSTOM_BOT" in results[0].skip_reason

    def test_skip_agent(self):
        """Mensagem do AGENT deve ser ignorada."""
        record = _valid_sqs_record(participant_role="AGENT")
        results = parse_sqs_batch(_sqs_event(record))

        assert results[0].chat_message is None
        assert "AGENT" in results[0].skip_reason

    def test_skip_system(self):
        """Mensagem do SYSTEM deve ser ignorada."""
        record = _valid_sqs_record(participant_role="SYSTEM")
        results = parse_sqs_batch(_sqs_event(record))

        assert results[0].chat_message is None
        assert "SYSTEM" in results[0].skip_reason

    def test_skip_event_type(self):
        """Type=EVENT deve ser ignorado."""
        record = _valid_sqs_record(event_type="EVENT")
        results = parse_sqs_batch(_sqs_event(record))

        assert results[0].chat_message is None
        assert "event_type_not_message" in results[0].skip_reason

    def test_skip_typing_content_type(self):
        """ContentType de typing deve ser ignorado."""
        record = _valid_sqs_record(
            content_type="application/vnd.amazonaws.connect.event.typing"
        )
        results = parse_sqs_batch(_sqs_event(record))

        assert results[0].chat_message is None
        assert "event_content_type" in results[0].skip_reason

    def test_skip_empty_content(self):
        """Conteúdo vazio deve ser ignorado."""
        record = _valid_sqs_record(content="")
        results = parse_sqs_batch(_sqs_event(record))

        assert results[0].chat_message is None
        assert "empty_content" in results[0].skip_reason

    def test_skip_whitespace_content(self):
        """Conteúdo apenas com espaços deve ser ignorado."""
        record = _valid_sqs_record(content="   ")
        results = parse_sqs_batch(_sqs_event(record))

        assert results[0].chat_message is None
        assert "empty_content" in results[0].skip_reason

    def test_skip_unsupported_content_type(self):
        """ContentType não-text/plain deve ser ignorado."""
        record = _valid_sqs_record(content_type="application/json")
        results = parse_sqs_batch(_sqs_event(record))

        assert results[0].chat_message is None
        assert "unsupported_content_type" in results[0].skip_reason

    def test_skip_does_not_raise(self):
        """Skip events nunca devem gerar EventParsingError."""
        record = _valid_sqs_record(participant_role="CUSTOM_BOT")
        results = parse_sqs_batch(_sqs_event(record))

        for r in results:
            assert not isinstance(r, EventParsingError)


# --- Testes de erro de parsing (JSON inválido → retry via SQS) ---


class TestParsingErrors:
    def test_invalid_json_body(self):
        """Body não-JSON deve gerar EventParsingError com sqs_message_id."""
        record = _sqs_record(body="isto não é json", sqs_message_id="sqs-bad-001")
        results = parse_sqs_batch(_sqs_event(record))

        assert len(results) == 1
        err = results[0]
        assert isinstance(err, EventParsingError)
        assert err.sqs_message_id == "sqs-bad-001"
        assert "JSON" in str(err)

    def test_invalid_json_in_message_field(self):
        """Campo Message não-JSON deve gerar EventParsingError."""
        envelope = {"Type": "Notification", "Message": "not json {{{"}
        record = _sqs_record(body=envelope, sqs_message_id="sqs-bad-002")
        results = parse_sqs_batch(_sqs_event(record))

        err = results[0]
        assert isinstance(err, EventParsingError)
        assert err.sqs_message_id == "sqs-bad-002"

    def test_missing_message_field(self):
        """Envelope SNS sem campo Message deve gerar EventParsingError."""
        envelope = {"Type": "Notification", "TopicArn": "arn:..."}
        record = _sqs_record(body=envelope, sqs_message_id="sqs-bad-003")
        results = parse_sqs_batch(_sqs_event(record))

        err = results[0]
        assert isinstance(err, EventParsingError)
        assert err.sqs_message_id == "sqs-bad-003"
        assert "Message" in str(err)

    def test_body_is_json_array(self):
        """Body JSON que é array (não objeto) deve gerar EventParsingError."""
        record = _sqs_record(body="[1, 2, 3]", sqs_message_id="sqs-bad-004")
        results = parse_sqs_batch(_sqs_event(record))

        err = results[0]
        assert isinstance(err, EventParsingError)
        assert err.sqs_message_id == "sqs-bad-004"

    def test_message_is_json_array(self):
        """Message que é JSON array deve gerar EventParsingError."""
        envelope = {"Type": "Notification", "Message": "[1, 2]"}
        record = _sqs_record(body=envelope, sqs_message_id="sqs-bad-005")
        results = parse_sqs_batch(_sqs_event(record))

        err = results[0]
        assert isinstance(err, EventParsingError)
        assert err.sqs_message_id == "sqs-bad-005"

    def test_missing_sqs_message_id(self):
        """Record SQS sem messageId deve gerar EventParsingError com id UNKNOWN."""
        record = {
            "body": json.dumps({"Type": "Notification", "Message": "{}"}),
            "eventSource": "aws:sqs",
        }
        results = parse_sqs_batch({"Records": [record]})

        err = results[0]
        assert isinstance(err, EventParsingError)
        assert err.sqs_message_id == "UNKNOWN"
        assert "messageId" in str(err).lower() or "UNKNOWN" in str(err)

    def test_parsing_error_identified_by_sqs_message_id(self):
        """O EventParsingError deve carregar o sqs_message_id para partial batch."""
        record = _sqs_record(body="{{bad", sqs_message_id="sqs-track-123")
        results = parse_sqs_batch(_sqs_event(record))

        err = results[0]
        assert isinstance(err, EventParsingError)
        assert err.sqs_message_id == "sqs-track-123"

    def test_mixed_batch_valid_and_invalid(self):
        """Batch com 1 válido e 1 inválido: válido é parsed, inválido é error."""
        valid = _valid_sqs_record(sqs_message_id="sqs-good")
        invalid = _sqs_record(body="not json", sqs_message_id="sqs-bad")
        results = parse_sqs_batch(_sqs_event(valid, invalid))

        assert len(results) == 2
        assert isinstance(results[0], ParsedSQSRecord)
        assert results[0].chat_message is not None
        assert isinstance(results[1], EventParsingError)
        assert results[1].sqs_message_id == "sqs-bad"


# --- Testes de imutabilidade ---


class TestModels:
    def test_connect_chat_message_is_frozen(self):
        """ConnectChatMessage deve ser imutável."""
        record = _valid_sqs_record()
        results = parse_sqs_batch(_sqs_event(record))
        msg = results[0].chat_message

        with pytest.raises(Exception):
            msg.content = "outra coisa"  # type: ignore
