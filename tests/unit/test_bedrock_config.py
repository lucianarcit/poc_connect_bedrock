"""Testes unitários para src/shared/bedrock_client/config.py."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from shared.bedrock_client.config import DEFAULT_SYSTEM_PROMPT, BedrockConfig, load_config
from shared.bedrock_client.exceptions import BedrockConfigurationError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove variáveis Bedrock do ambiente antes de cada teste."""
    for var in (
        "BEDROCK_MODEL_ID",
        "BEDROCK_MAX_TOKENS",
        "BEDROCK_TEMPERATURE",
        "BEDROCK_SYSTEM_PROMPT",
        "BEDROCK_TIMEOUT_SECONDS",
        "AWS_REGION",
    ):
        monkeypatch.delenv(var, raising=False)


class TestModelId:
    """Testes de validação do BEDROCK_MODEL_ID."""

    def test_missing_model_id_raises(self):
        with pytest.raises(BedrockConfigurationError) as exc_info:
            load_config()
        assert "BEDROCK_MODEL_ID" in str(exc_info.value)
        assert exc_info.value.error_code == "MISSING_MODEL_ID"

    def test_empty_model_id_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "")
        with pytest.raises(BedrockConfigurationError) as exc_info:
            load_config()
        assert exc_info.value.error_code == "MISSING_MODEL_ID"

    def test_whitespace_model_id_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "   ")
        with pytest.raises(BedrockConfigurationError):
            load_config()

    def test_valid_model_id(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")
        config = load_config()
        assert config.model_id == "us.amazon.nova-lite-v1:0"


class TestMaxTokens:
    """Testes de validação do BEDROCK_MAX_TOKENS."""

    def test_default_1024(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        config = load_config()
        assert config.max_tokens == 1024

    def test_zero_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_MAX_TOKENS", "0")
        with pytest.raises(BedrockConfigurationError) as exc_info:
            load_config()
        assert exc_info.value.error_code == "INVALID_MAX_TOKENS"

    def test_above_4096_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_MAX_TOKENS", "5000")
        with pytest.raises(BedrockConfigurationError):
            load_config()

    def test_valid_1(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_MAX_TOKENS", "1")
        config = load_config()
        assert config.max_tokens == 1

    def test_valid_4096(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_MAX_TOKENS", "4096")
        config = load_config()
        assert config.max_tokens == 4096

    def test_non_integer_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_MAX_TOKENS", "abc")
        with pytest.raises(BedrockConfigurationError):
            load_config()


class TestTemperature:
    """Testes de validação do BEDROCK_TEMPERATURE."""

    def test_default_07(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        config = load_config()
        assert config.temperature == 0.7

    def test_valid_0(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_TEMPERATURE", "0.0")
        config = load_config()
        assert config.temperature == 0.0

    def test_valid_1(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_TEMPERATURE", "1.0")
        config = load_config()
        assert config.temperature == 1.0

    def test_above_1_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_TEMPERATURE", "1.5")
        with pytest.raises(BedrockConfigurationError) as exc_info:
            load_config()
        assert exc_info.value.error_code == "INVALID_TEMPERATURE"

    def test_negative_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_TEMPERATURE", "-0.1")
        with pytest.raises(BedrockConfigurationError):
            load_config()

    def test_non_float_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_TEMPERATURE", "quente")
        with pytest.raises(BedrockConfigurationError):
            load_config()


class TestTimeout:
    """Testes de validação do BEDROCK_TIMEOUT_SECONDS."""

    def test_default_20(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        config = load_config()
        assert config.timeout_seconds == 20

    def test_below_5_raises(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_TIMEOUT_SECONDS", "4")
        with pytest.raises(BedrockConfigurationError) as exc_info:
            load_config()
        assert exc_info.value.error_code == "INVALID_TIMEOUT"

    def test_valid_5(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_TIMEOUT_SECONDS", "5")
        config = load_config()
        assert config.timeout_seconds == 5

    def test_valid_55(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_TIMEOUT_SECONDS", "55")
        config = load_config()
        assert config.timeout_seconds == 55


class TestSystemPrompt:
    """Testes do system prompt."""

    def test_default_contains_required_instructions(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        config = load_config()
        prompt = config.system_prompt
        assert "Responda sempre em português brasileiro" in prompt
        assert "Seja claro e objetivo" in prompt
        assert "agente virtual de suporte" in prompt
        assert "Não invente informações" in prompt
        assert "não tiver dados suficientes" in prompt

    def test_custom_override(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_SYSTEM_PROMPT", "Responda em inglês.")
        config = load_config()
        assert config.system_prompt == "Responda em inglês."

    def test_empty_override_uses_default(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("BEDROCK_SYSTEM_PROMPT", "")
        config = load_config()
        assert config.system_prompt == DEFAULT_SYSTEM_PROMPT


class TestRegion:
    """Testes da região AWS."""

    def test_default_us_east_1(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        config = load_config()
        assert config.region == "us-east-1"

    def test_custom_region(self, monkeypatch):
        monkeypatch.setenv("BEDROCK_MODEL_ID", "test-model")
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        config = load_config()
        assert config.region == "eu-west-1"
