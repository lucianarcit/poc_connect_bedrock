"""Testes unitários para src/shared/bedrock_client/client.py."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError

from shared.bedrock_client.client import BedrockClient
from shared.bedrock_client.exceptions import (
    BedrockConfigurationError,
    BedrockFatalError,
    BedrockTimeoutError,
    BedrockTransientError,
)


@pytest.fixture(autouse=True)
def _env_vars(monkeypatch):
    """Configuração mínima válida para todos os testes."""
    monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model-id")
    monkeypatch.setenv("BEDROCK_MAX_TOKENS", "512")
    monkeypatch.setenv("BEDROCK_TEMPERATURE", "0.5")
    monkeypatch.setenv("BEDROCK_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@pytest.fixture
def mock_boto3_client():
    """Mock do boto3.client('bedrock-runtime')."""
    with patch("shared.bedrock_client.client.boto3.client") as mock_client:
        mock_bedrock = MagicMock()
        mock_client.return_value = mock_bedrock
        yield mock_bedrock


def _make_converse_response(text: str = "Resposta do modelo") -> dict:
    """Helper para criar resposta da Converse API."""
    return {
        "output": {
            "message": {
                "content": [{"text": text}]
            }
        }
    }


def _make_client_error(code: str, message: str = "Error") -> ClientError:
    """Helper para criar ClientError com código específico."""
    return ClientError(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name="Converse",
    )


class TestInitialization:
    """Testes de inicialização do BedrockClient."""

    def test_successful_init(self, mock_boto3_client):
        client = BedrockClient()
        assert client.model_id == "test-model-id"

    def test_missing_model_id_raises(self, monkeypatch, mock_boto3_client):
        monkeypatch.delenv("BEDROCK_MODEL_ID")
        with pytest.raises(BedrockConfigurationError):
            BedrockClient()

    def test_boto3_client_created_with_config(self, mock_boto3_client):
        with patch("shared.bedrock_client.client.boto3.client") as mock_create:
            mock_create.return_value = MagicMock()
            BedrockClient()
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["region_name"] == "us-east-1"


class TestConverseSuccess:
    """Testes de chamada converse com sucesso."""

    def test_returns_extracted_text(self, mock_boto3_client):
        mock_boto3_client.converse.return_value = _make_converse_response("Olá!")
        client = BedrockClient()
        result = client.converse("Qual é a capital?", correlation_id="test-123")
        assert result == "Olá!"

    def test_builds_correct_request(self, mock_boto3_client):
        mock_boto3_client.converse.return_value = _make_converse_response()
        client = BedrockClient()
        client.converse("Pergunta")
        call_kwargs = mock_boto3_client.converse.call_args[1]
        assert call_kwargs["modelId"] == "test-model-id"
        assert call_kwargs["messages"] == [
            {"role": "user", "content": [{"text": "Pergunta"}]}
        ]
        assert call_kwargs["inferenceConfig"]["maxTokens"] == 512
        assert call_kwargs["inferenceConfig"]["temperature"] == 0.5
        assert len(call_kwargs["system"]) == 1
        assert "text" in call_kwargs["system"][0]


class TestTimeoutProtection:
    """Testes de proteção de timeout."""

    def test_insufficient_remaining_time_raises(self, mock_boto3_client):
        client = BedrockClient()
        # timeout=10s, margem=5s, necessário=15000ms
        with pytest.raises(BedrockTimeoutError) as exc_info:
            client.converse("msg", remaining_time_ms=14000)
        assert "insuficiente" in str(exc_info.value).lower() or "Insufficient" in str(exc_info.value)

    def test_sufficient_remaining_time_calls_bedrock(self, mock_boto3_client):
        mock_boto3_client.converse.return_value = _make_converse_response()
        client = BedrockClient()
        result = client.converse("msg", remaining_time_ms=20000)
        assert result == "Resposta do modelo"
        mock_boto3_client.converse.assert_called_once()

    def test_none_remaining_time_skips_check(self, mock_boto3_client):
        mock_boto3_client.converse.return_value = _make_converse_response()
        client = BedrockClient()
        result = client.converse("msg", remaining_time_ms=None)
        assert result == "Resposta do modelo"

    def test_read_timeout_raises_bedrock_timeout(self, mock_boto3_client):
        mock_boto3_client.converse.side_effect = ReadTimeoutError(endpoint_url="https://bedrock.us-east-1.amazonaws.com")
        client = BedrockClient()
        with pytest.raises(BedrockTimeoutError):
            client.converse("msg")

    def test_connect_timeout_raises_bedrock_timeout(self, mock_boto3_client):
        mock_boto3_client.converse.side_effect = ConnectTimeoutError(endpoint_url="https://bedrock.us-east-1.amazonaws.com")
        client = BedrockClient()
        with pytest.raises(BedrockTimeoutError):
            client.converse("msg")


class TestTransientErrors:
    """Testes de erros transitórios (retry apropriado)."""

    @pytest.mark.parametrize("error_code", [
        "ThrottlingException",
        "ServiceUnavailableException",
        "ModelTimeoutException",
        "InternalServerException",
    ])
    def test_transient_errors(self, mock_boto3_client, error_code):
        mock_boto3_client.converse.side_effect = _make_client_error(error_code)
        client = BedrockClient()
        with pytest.raises(BedrockTransientError) as exc_info:
            client.converse("msg")
        assert exc_info.value.error_code == error_code


class TestFatalErrors:
    """Testes de erros fatais (sem retry, FAILED_FINAL)."""

    @pytest.mark.parametrize("error_code", [
        "AccessDeniedException",
        "ValidationException",
        "ModelNotFoundException",
        "ResourceNotFoundException",
    ])
    def test_fatal_errors(self, mock_boto3_client, error_code):
        mock_boto3_client.converse.side_effect = _make_client_error(error_code)
        client = BedrockClient()
        with pytest.raises(BedrockFatalError) as exc_info:
            client.converse("msg")
        assert exc_info.value.error_code == error_code

    def test_unknown_client_error_is_fatal(self, mock_boto3_client):
        mock_boto3_client.converse.side_effect = _make_client_error("SomeNewException")
        client = BedrockClient()
        with pytest.raises(BedrockFatalError) as exc_info:
            client.converse("msg")
        assert exc_info.value.error_code == "SomeNewException"


class TestLogSanitization:
    """Testes de que conteúdo sensível NUNCA aparece nos logs."""

    def test_user_message_not_in_logs(self, mock_boto3_client, caplog):
        mock_boto3_client.converse.return_value = _make_converse_response("Resposta secreta")
        client = BedrockClient()

        secret_message = "MENSAGEM_SECRETA_DO_USUARIO_12345"
        with caplog.at_level(logging.DEBUG, logger="shared.bedrock_client"):
            client.converse(secret_message, correlation_id="corr-id")

        # Conteúdo da mensagem NUNCA deve aparecer nos logs
        for record in caplog.records:
            assert secret_message not in record.getMessage()
            # Verificar também nos extras formatados
            log_text = str(record.__dict__)
            assert secret_message not in log_text

    def test_model_response_not_in_logs(self, mock_boto3_client, caplog):
        secret_response = "RESPOSTA_SECRETA_DO_MODELO_67890"
        mock_boto3_client.converse.return_value = _make_converse_response(secret_response)
        client = BedrockClient()

        with caplog.at_level(logging.DEBUG, logger="shared.bedrock_client"):
            client.converse("pergunta qualquer", correlation_id="corr-id")

        for record in caplog.records:
            assert secret_response not in record.getMessage()
            log_text = str(record.__dict__)
            assert secret_response not in log_text

    def test_latency_present_in_logs(self, mock_boto3_client, caplog):
        mock_boto3_client.converse.return_value = _make_converse_response()
        client = BedrockClient()

        with caplog.at_level(logging.INFO, logger="shared.bedrock_client"):
            client.converse("msg", correlation_id="test-corr")

        info_records = [r for r in caplog.records if r.levelname == "INFO" and "completed" in r.getMessage()]
        assert len(info_records) >= 1
        record = info_records[-1]
        assert hasattr(record, "latency_ms")
        assert hasattr(record, "model_id")

    def test_correlation_id_in_logs(self, mock_boto3_client, caplog):
        mock_boto3_client.converse.return_value = _make_converse_response()
        client = BedrockClient()

        with caplog.at_level(logging.INFO, logger="shared.bedrock_client"):
            client.converse("msg", correlation_id="my-corr-id-123")

        info_records = [r for r in caplog.records if r.levelname == "INFO" and "completed" in r.getMessage()]
        assert len(info_records) >= 1
        assert info_records[-1].correlation_id == "my-corr-id-123"
