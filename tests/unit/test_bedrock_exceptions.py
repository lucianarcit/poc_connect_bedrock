"""Testes unitários para src/shared/bedrock_client/exceptions.py."""

from __future__ import annotations

import pytest

from shared.bedrock_client.exceptions import (
    BedrockConfigurationError,
    BedrockError,
    BedrockFatalError,
    BedrockTimeoutError,
    BedrockTransientError,
)


class TestExceptionHierarchy:
    """Testes da hierarquia de herança."""

    def test_bedrock_error_is_exception(self):
        assert issubclass(BedrockError, Exception)

    def test_configuration_error_is_bedrock_error(self):
        assert issubclass(BedrockConfigurationError, BedrockError)

    def test_transient_error_is_bedrock_error(self):
        assert issubclass(BedrockTransientError, BedrockError)

    def test_fatal_error_is_bedrock_error(self):
        assert issubclass(BedrockFatalError, BedrockError)

    def test_timeout_error_is_transient(self):
        """BedrockTimeoutError é subtipo de BedrockTransientError — permite retry."""
        assert issubclass(BedrockTimeoutError, BedrockTransientError)

    def test_timeout_is_not_fatal(self):
        assert not issubclass(BedrockTimeoutError, BedrockFatalError)


class TestErrorAttributes:
    """Testes de atributos das exceções."""

    def test_error_code_attribute(self):
        err = BedrockError("mensagem", error_code="TestCode")
        assert err.error_code == "TestCode"
        assert str(err) == "mensagem"

    def test_error_code_none_by_default(self):
        err = BedrockError("sem código")
        assert err.error_code is None

    def test_configuration_error_with_code(self):
        err = BedrockConfigurationError("model missing", error_code="MISSING_MODEL_ID")
        assert err.error_code == "MISSING_MODEL_ID"

    def test_transient_error_with_code(self):
        err = BedrockTransientError("throttled", error_code="ThrottlingException")
        assert err.error_code == "ThrottlingException"

    def test_fatal_error_with_code(self):
        err = BedrockFatalError("access denied", error_code="AccessDeniedException")
        assert err.error_code == "AccessDeniedException"

    def test_timeout_error_with_code(self):
        err = BedrockTimeoutError("read timeout", error_code="ReadTimeoutError")
        assert err.error_code == "ReadTimeoutError"


class TestIsInstanceChecks:
    """Testes de isinstance para uso no Integrator."""

    def test_catching_transient_catches_timeout(self):
        """O Integrator pode capturar BedrockTransientError para pegar também timeout."""
        err = BedrockTimeoutError("timeout")
        assert isinstance(err, BedrockTransientError)
        assert isinstance(err, BedrockError)

    def test_catching_fatal_does_not_catch_transient(self):
        err = BedrockTransientError("retry me")
        assert not isinstance(err, BedrockFatalError)

    def test_catching_bedrock_error_catches_all(self):
        errors = [
            BedrockConfigurationError("config"),
            BedrockTransientError("transient"),
            BedrockFatalError("fatal"),
            BedrockTimeoutError("timeout"),
        ]
        for err in errors:
            assert isinstance(err, BedrockError)
