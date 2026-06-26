"""
Testes que validam o formato da resposta da Initializer para Amazon Connect.

O bloco InvokeLambdaFunction com ResponseValidation.ResponseType = STRING_MAP
exige que a Lambda retorne um dicionário onde:
- Todas as chaves são strings
- Todos os valores são strings
- Não há estruturas aninhadas (dicts, lists, None, bool, int)
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from initializer.handler import handler


def _make_connect_event(
    contact_id: str = "test-contact-001",
    instance_arn: str = "arn:aws:connect:us-east-1:123456789012:instance/test-instance-id",
    channel: str = "CHAT",
) -> dict:
    """Cria evento no formato do Contact Flow."""
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
    """Valida que a resposta é compatível com Amazon Connect STRING_MAP."""
    assert isinstance(response, dict), f"Response must be dict, got {type(response)}"
    for key, value in response.items():
        assert isinstance(key, str), f"Key '{key}' must be str, got {type(key)}"
        assert isinstance(value, str), f"Value for '{key}' must be str, got {type(value).__name__}: {value!r}"
        # Não pode ser 'None' como string representando None
        assert value != "None", f"Value for '{key}' is literal 'None' — use empty string instead"


class TestResponseFormatStringMap:
    """Valida que todas as respostas possíveis são STRING_MAP válidos."""

    @patch("initializer.handler._get_clients")
    def test_invalid_event_returns_string_map(self, mock_clients):
        """Evento inválido retorna STRING_MAP com status ERROR."""
        response = handler({}, None)
        _assert_valid_string_map(response)
        assert response["status"] == "ERROR"
        assert response["botInitialized"] == "false"

    @patch("initializer.handler._get_clients")
    def test_non_chat_channel_returns_string_map(self, mock_clients):
        """Canal não-CHAT retorna STRING_MAP com status ERROR."""
        event = _make_connect_event(channel="VOICE")
        response = handler(event, None)
        _assert_valid_string_map(response)
        assert response["status"] == "ERROR"

    @patch("initializer.handler._get_clients")
    @patch("initializer.service.InitializerService.initialize")
    def test_success_returns_string_map(self, mock_init, mock_clients):
        """Sucesso retorna STRING_MAP com status SUCCESS."""
        mock_init.return_value = {"status": "SUCCESS", "botInitialized": "true"}
        mock_clients.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())

        event = _make_connect_event()
        response = handler(event, None)
        _assert_valid_string_map(response)
        assert response["status"] == "SUCCESS"
        assert response["botInitialized"] == "true"

    @patch("initializer.handler._get_clients")
    @patch("initializer.service.InitializerService.initialize")
    def test_error_returns_string_map(self, mock_init, mock_clients):
        """Erro na inicialização retorna STRING_MAP."""
        mock_init.return_value = {"status": "ERROR", "botInitialized": "false", "errorCode": "INITIALIZATION_FAILED"}
        mock_clients.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())

        event = _make_connect_event()
        response = handler(event, None)
        _assert_valid_string_map(response)
        assert response["status"] == "ERROR"

    @patch("initializer.handler._get_clients")
    @patch("initializer.service.InitializerService.initialize")
    def test_no_nested_structures(self, mock_init, mock_clients):
        """Resposta não deve conter dicts, lists, booleans ou None."""
        mock_init.return_value = {"status": "SUCCESS", "botInitialized": "true"}
        mock_clients.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())

        event = _make_connect_event()
        response = handler(event, None)

        for key, value in response.items():
            assert not isinstance(value, dict), f"Nested dict in '{key}'"
            assert not isinstance(value, list), f"List in '{key}'"
            assert not isinstance(value, bool), f"Bool in '{key}' (use 'true'/'false' strings)"
            assert value is not None, f"None in '{key}' (use empty string)"
            assert not isinstance(value, (int, float)), f"Number in '{key}' (use str())"

    @patch("initializer.handler._get_clients")
    @patch("initializer.service.InitializerService.initialize")
    def test_all_known_return_paths(self, mock_init, mock_clients):
        """Testa todos os retornos conhecidos do InitializerService."""
        mock_clients.return_value = (MagicMock(), MagicMock(), MagicMock(), MagicMock())
        event = _make_connect_event()

        known_responses = [
            {"status": "SUCCESS", "botInitialized": "true"},
            {"status": "ERROR", "botInitialized": "false", "errorCode": "INITIALIZATION_IN_PROGRESS"},
            {"status": "ERROR", "botInitialized": "false", "errorCode": "INITIALIZATION_FAILED"},
        ]

        for resp in known_responses:
            mock_init.return_value = resp
            result = handler(event, None)
            _assert_valid_string_map(result)
