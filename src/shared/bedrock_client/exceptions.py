"""Exceções do módulo BedrockClient.

Hierarquia:
    BedrockError (base)
    ├── BedrockConfigurationError  — variável ausente ou valor inválido
    ├── BedrockTransientError      — retry é apropriado
    │   └── BedrockTimeoutError    — timeout (subtipo de transitório)
    └── BedrockFatalError          — não fazer retry, marcar FAILED_FINAL
"""

from __future__ import annotations


class BedrockError(Exception):
    """Exceção base do módulo BedrockClient."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(message)


class BedrockConfigurationError(BedrockError):
    """Erro de configuração — variável ausente ou valor inválido.

    Lançado na inicialização do BedrockClient. Impede processamento de qualquer mensagem.
    """

    pass


class BedrockTransientError(BedrockError):
    """Erro transitório — retry é apropriado.

    O Integrator deve falhar o item SQS para retry (batchItemFailure).
    Após maxReceiveCount=3, mensagem vai para DLQ.
    """

    pass


class BedrockTimeoutError(BedrockTransientError):
    """Timeout da chamada ao Bedrock — subtipo de transitório, permite retry.

    Pode ser:
    - Tempo restante da Lambda insuficiente (pré-chamada)
    - read_timeout do botocore excedido
    - connect_timeout do botocore excedido
    """

    pass


class BedrockFatalError(BedrockError):
    """Erro fatal — não fazer retry, marcar FAILED_FINAL.

    O Integrator deve enviar mensagem de erro ao usuário e marcar FAILED_FINAL na idempotência.
    """

    pass
