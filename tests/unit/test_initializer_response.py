"""
Testes de formato STRING_MAP e idempotência da Initializer.

Valida que:
- Todos os retornos são dict[str, str] (STRING_MAP)
- Dupla invocação para o mesmo ContactId não causa falha
- Wait for activation funciona corretamente
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from initializer.handler import handler, _validate_string_map
from initializer.service import InitializerService, InitializationContext


def _make_connect_event(
    contact_id: str = "test-contact-001",
    instance_arn: str = "arn:aws:connect:us-east-1:123456789012:instance/test-instance-id",
    channel: str = "CHAT",
) -> dict:
    return {
        "Details": {
            "ContactData": {
                "ContactId": contact_id,
                "InitialContactId": contact_id,
                "Channel": channel,
                "InstanceARN": instance_arn,
            },
            "Parameters": {},
        },
        "Name": "ContactFlowEvent",
    }


def _assert_valid_string_map(response: dict) -> None:
    assert isinstance(response, dict)
    for key, value in response.items():
        assert isinstance(key, str), f"Key '{key}' not str"
        assert isinstance(value, str), f"Value for '{key}' is {type(value).__name__}: {value!r}"


class TestValidateStringMap:
    def test_valid(self):
        assert _validate_string_map({"a": "b"}) == {"a": "b"}

    def test_non_dict_raises(self):
        with pytest.raises(TypeError):
            _validate_string_map("string")

    def test_non_string_key_raises(self):
        with pytest.raises(TypeError):
            _validate_string_map({1: "val"})

    def test_non_string_value_raises(self):
        with pytest.raises(TypeError):
            _validate_string_map({"key": 123})

    def test_none_value_raises(self):
        with pytest.raises(TypeError):
            _validate_string_map({"key": None})

    def test_bool_value_raises(self):
        with pytest.raises(TypeError):
            _validate_string_map({"key": True})


class TestHandlerStringMap:
    @patch("initializer.handler._get_clients")
    def test_invalid_event_returns_string_map(self, mock_clients):
        response = handler({}, None)
        _assert_valid_string_map(response)
        assert response["status"] == "ERROR"

    @patch("initializer.handler._get_clients")
    def test_non_chat_returns_string_map(self, mock_clients):
        event = _make_connect_event(channel="VOICE")
        response = handler(event, None)
        _assert_valid_string_map(response)
        assert response["status"] == "ERROR"

    @patch("initializer.handler._get_clients")
    @patch("initializer.service.InitializerService.initialize")
    def test_success_returns_string_map(self, mock_init, mock_clients):
        mock_init.return_value = {"status": "SUCCESS", "botInitialized": "true"}
        mock_clients.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        response = handler(_make_connect_event(), None)
        _assert_valid_string_map(response)
        assert response["status"] == "SUCCESS"

    @patch("initializer.handler._get_clients")
    @patch("initializer.service.InitializerService.initialize")
    def test_unhandled_exception_returns_string_map(self, mock_init, mock_clients):
        mock_init.side_effect = RuntimeError("unexpected")
        mock_clients.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        response = handler(_make_connect_event(), None)
        _assert_valid_string_map(response)
        assert response["status"] == "ERROR"
        assert response["errorCode"] == "UNHANDLED_EXCEPTION"


class TestDualInvocationIdempotency:
    """Testa o comportamento quando a Initializer é invocada duas vezes para o mesmo ContactId."""

    def _make_service(self, dynamodb_mock):
        return InitializerService(
            connect_client=MagicMock(),
            participant_client=MagicMock(),
            kms_client=MagicMock(),
            dynamodb_client=dynamodb_mock,
            sns_topic_arn="arn:aws:sns:us-east-1:123456789012:topic",
            kms_key_id="key-123",
            table_name="test-sessions",
            lease_seconds=30,
        )

    def _ctx(self, contact_id="contact-001"):
        return InitializationContext(
            contact_id=contact_id,
            instance_id="inst-001",
            initial_contact_id=contact_id,
            channel="CHAT",
        )

    def test_active_complete_returns_success(self):
        """Se sessão já ACTIVE_COMPLETE, retorna SUCCESS imediato."""
        dynamodb = MagicMock()
        dynamodb.get_item.return_value = {
            "Item": {
                "pk": {"S": "CONTACT#contact-001"},
                "status": {"S": "ACTIVE"},
                "participant_id": {"S": "part-123"},
                "connection_token_encrypted": {"B": b"\x01\x02"},
                "connection_token_expiry": {"S": "2030-01-01T00:00:00Z"},
            }
        }
        service = self._make_service(dynamodb)
        result = service.initialize(self._ctx())
        assert result == {"status": "SUCCESS", "botInitialized": "true"}

    @patch("time.sleep", return_value=None)
    def test_initializing_then_active_returns_success(self, mock_sleep):
        """Se sessão está INITIALIZING mas vira ACTIVE durante wait, retorna SUCCESS."""
        dynamodb = MagicMock()
        now = int(time.time())

        # Primeira chamada: INITIALIZING com lease ativo
        # Segunda chamada (no wait): ACTIVE_COMPLETE
        dynamodb.get_item.side_effect = [
            # _check_existing_session inicial
            {"Item": {
                "pk": {"S": "CONTACT#contact-001"},
                "status": {"S": "INITIALIZING"},
                "initialization_lease_expires_at": {"N": str(now + 20)},
                "participant_id": {"S": ""},
                "connection_token_encrypted": {"B": b"\x00"},
                "connection_token_expiry": {"S": ""},
            }},
            # _wait_for_activation → _check_existing_session (poll 1)
            {"Item": {
                "pk": {"S": "CONTACT#contact-001"},
                "status": {"S": "ACTIVE"},
                "participant_id": {"S": "part-123"},
                "connection_token_encrypted": {"B": b"\x01\x02"},
                "connection_token_expiry": {"S": "2030-01-01T00:00:00Z"},
            }},
        ]

        service = self._make_service(dynamodb)
        result = service.initialize(self._ctx())
        assert result == {"status": "SUCCESS", "botInitialized": "true"}

    @patch("time.sleep", return_value=None)
    def test_initializing_timeout_returns_error(self, mock_sleep):
        """Se sessão permanece INITIALIZING além do wait, retorna erro rastreável."""
        dynamodb = MagicMock()
        now = int(time.time())

        # Sempre retorna INITIALIZING (lease ativo)
        dynamodb.get_item.return_value = {
            "Item": {
                "pk": {"S": "CONTACT#contact-001"},
                "status": {"S": "INITIALIZING"},
                "initialization_lease_expires_at": {"N": str(now + 20)},
                "participant_id": {"S": ""},
                "connection_token_encrypted": {"B": b"\x00"},
                "connection_token_expiry": {"S": ""},
            }
        }

        service = self._make_service(dynamodb)
        # Use max_wait muito curto para não bloquear o teste
        service._lease_seconds = 30
        result = service.initialize(self._ctx())

        _assert_valid_string_map(result)
        assert result["status"] == "ERROR"
        assert "TIMEOUT" in result.get("errorCode", "") or "PROGRESS" in result.get("errorCode", "")

    def test_not_found_proceeds_with_initialization(self):
        """Se sessão NOT_FOUND, procede com reserva e inicialização."""
        dynamodb = MagicMock()
        connect = MagicMock()
        participant = MagicMock()
        kms = MagicMock()

        # get_item: não encontra
        dynamodb.get_item.return_value = {}
        # put_item: sucesso (reserva)
        dynamodb.put_item.return_value = {}
        # update_item: sucesso (ativação)
        dynamodb.update_item.return_value = {}

        # Connect APIs
        connect.start_contact_streaming.return_value = {"StreamingId": "stream-1"}
        connect.create_participant.return_value = {
            "ParticipantId": "part-1",
            "ParticipantCredentials": {"ParticipantToken": "pt-token"},
        }
        participant.create_participant_connection.return_value = {
            "ConnectionCredentials": {
                "ConnectionToken": "ct-token",
                "Expiry": "2030-01-01T00:00:00Z",
            }
        }
        kms.encrypt.return_value = {"CiphertextBlob": b"\x01\x02\x03"}

        service = InitializerService(
            connect_client=connect,
            participant_client=participant,
            kms_client=kms,
            dynamodb_client=dynamodb,
            sns_topic_arn="arn:aws:sns:us-east-1:123:topic",
            kms_key_id="key-1",
            table_name="test",
            lease_seconds=30,
        )
        result = service.initialize(self._ctx())
        _assert_valid_string_map(result)
        assert result["status"] == "SUCCESS"

    def test_client_tokens_deterministic(self):
        """Mesmos inputs produzem mesmos ClientTokens (idempotência de retry)."""
        from initializer.service import generate_streaming_client_token, generate_participant_client_token

        t1 = generate_streaming_client_token("inst-1", "contact-1", "arn:sns:topic")
        t2 = generate_streaming_client_token("inst-1", "contact-1", "arn:sns:topic")
        assert t1 == t2

        p1 = generate_participant_client_token("inst-1", "contact-1")
        p2 = generate_participant_client_token("inst-1", "contact-1")
        assert p1 == p2
