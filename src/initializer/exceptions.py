"""Exceções da Lambda Initializer."""

from __future__ import annotations


class InitializerError(Exception):
    """Erro base da Initializer."""

    def __init__(self, message: str, error_code: str = "INITIALIZATION_FAILED") -> None:
        self.error_code = error_code
        super().__init__(message)


class InvalidEventError(InitializerError):
    """Evento recebido é inválido ou incompleto."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_EVENT")
