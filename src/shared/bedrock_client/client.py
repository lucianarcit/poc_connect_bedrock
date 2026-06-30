"""Cliente Amazon Bedrock Converse API.

Responsabilidades:
- Criar e gerenciar cliente boto3 bedrock-runtime
- Chamar o método converse com system prompt, messages e inferenceConfig
- Extrair texto da resposta via response_parser
- Classificar erros em transitórios/fatais
- Registrar latência e métricas sem expor conteúdo sensível
- Verificar tempo restante da Lambda antes de chamar Bedrock
- Aplicar timeout via botocore config

Segurança de logging:
- NUNCA registrar conteúdo da mensagem do usuário em NENHUM nível
- NUNCA registrar conteúdo da resposta do modelo em NENHUM nível
- Apenas metadados: content_length, response_length, latency_ms, model_id
"""

from __future__ import annotations

import logging
import time
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    ReadTimeoutError,
)

from shared.bedrock_client.config import BedrockConfig, load_config
from shared.bedrock_client.exceptions import (
    BedrockConfigurationError,
    BedrockFatalError,
    BedrockTimeoutError,
    BedrockTransientError,
)
from shared.bedrock_client.response_parser import extract_text_from_response

logger = logging.getLogger(__name__)

# Erros AWS classificados como transitórios (retry apropriado)
_TRANSIENT_ERROR_CODES = frozenset({
    "ThrottlingException",
    "ServiceUnavailableException",
    "ModelTimeoutException",
    "InternalServerException",
})

# Erros AWS classificados como fatais (sem retry, FAILED_FINAL)
_FATAL_ERROR_CODES = frozenset({
    "AccessDeniedException",
    "ValidationException",
    "ModelNotFoundException",
    "ResourceNotFoundException",
    "ModelNotReadyException",
})

# Margem mínima em ms que deve restar após o timeout do Bedrock
_MIN_MARGIN_MS = 5000


class BedrockClient:
    """Abstração para Amazon Bedrock Converse API.

    Responsabilidades:
    - Construir e enviar requisições à Converse API
    - Extrair texto da resposta (multi-bloco)
    - Classificar erros em transitórios/fatais
    - Registrar latência sem conteúdo sensível
    - Aplicar timeout configurável com verificação de tempo restante

    Raises:
        BedrockConfigurationError: Se BEDROCK_MODEL_ID ausente ou valores inválidos.
    """

    def __init__(self) -> None:
        """Inicializa o cliente lendo configuração de variáveis de ambiente.

        Raises:
            BedrockConfigurationError: se BEDROCK_MODEL_ID não definido/vazio
                ou se valores numéricos estão fora dos limites válidos.
        """
        self._config: BedrockConfig = load_config()

        botocore_config = BotocoreConfig(
            connect_timeout=5,
            read_timeout=self._config.timeout_seconds,
            retries={"max_attempts": 0},  # Sem retry interno — gerenciado pelo SQS
        )

        self._client = boto3.client(
            "bedrock-runtime",
            region_name=self._config.region,
            config=botocore_config,
        )

        logger.info(
            "BedrockClient initialized",
            extra={
                "model_id": self._config.model_id,
                "region": self._config.region,
                "timeout_seconds": self._config.timeout_seconds,
                "max_tokens": self._config.max_tokens,
            },
        )

    @property
    def model_id(self) -> str:
        """Retorna o model ID configurado."""
        return self._config.model_id

    def converse(
        self,
        user_message: str,
        correlation_id: str | None = None,
        remaining_time_ms: int | None = None,
    ) -> str:
        """Envia mensagem do usuário ao Bedrock e retorna texto da resposta.

        Args:
            user_message: Texto do usuário (1 a 4096 caracteres).
            correlation_id: ID de correlação para logs (opcional).
            remaining_time_ms: Milissegundos restantes da Lambda
                (via context.get_remaining_time_in_millis()). Se fornecido,
                aborta antes da chamada HTTP se tempo insuficiente.

        Returns:
            Texto extraído da resposta do modelo. Fallback se sem conteúdo.

        Raises:
            BedrockTransientError: throttling, service unavailable.
            BedrockTimeoutError: timeout (subtipo de transient).
            BedrockFatalError: access denied, validation error, erro inesperado.
        """
        log_extra: dict[str, Any] = {
            "model_id": self._config.model_id,
            "content_length": len(user_message),
        }
        if correlation_id:
            log_extra["correlation_id"] = correlation_id

        # Verificação pré-chamada de tempo restante
        required_ms = (self._config.timeout_seconds * 1000) + _MIN_MARGIN_MS
        if remaining_time_ms is not None and remaining_time_ms < required_ms:
            logger.warning(
                "Insufficient remaining Lambda time for Bedrock call",
                extra={
                    **log_extra,
                    "remaining_time_ms": remaining_time_ms,
                    "required_ms": required_ms,
                    "error_code": "INSUFFICIENT_TIME",
                    "error_category": "TRANSIENT",
                },
            )
            raise BedrockTimeoutError(
                f"Tempo restante da Lambda ({remaining_time_ms}ms) insuficiente "
                f"para chamada Bedrock (necessário: {required_ms}ms)",
                error_code="INSUFFICIENT_TIME",
            )

        # Montar requisição
        request_params = self._build_request(user_message)

        # Executar chamada com medição de latência
        start_time = time.time()
        try:
            response = self._client.converse(**request_params)
            latency_ms = (time.time() - start_time) * 1000

            # Extrair texto da resposta
            result_text = extract_text_from_response(response)

            logger.info(
                "Bedrock converse completed",
                extra={
                    **log_extra,
                    "latency_ms": round(latency_ms, 1),
                    "response_length": len(result_text),
                },
            )

            return result_text

        except (ReadTimeoutError, ConnectTimeoutError) as e:
            latency_ms = (time.time() - start_time) * 1000
            error_code = type(e).__name__
            logger.warning(
                "Bedrock converse timeout",
                extra={
                    **log_extra,
                    "latency_ms": round(latency_ms, 1),
                    "error_code": error_code,
                    "error_category": "TRANSIENT",
                },
            )
            raise BedrockTimeoutError(
                f"Timeout na chamada ao Bedrock: {error_code}",
                error_code=error_code,
            ) from e

        except ClientError as e:
            latency_ms = (time.time() - start_time) * 1000
            error_code = e.response.get("Error", {}).get("Code", "UnknownError")
            self._handle_client_error(e, error_code, latency_ms, log_extra)

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_code = type(e).__name__
            logger.error(
                "Bedrock converse unexpected error",
                extra={
                    **log_extra,
                    "latency_ms": round(latency_ms, 1),
                    "error_code": error_code,
                    "error_category": "FATAL",
                },
            )
            raise BedrockFatalError(
                f"Erro inesperado ao chamar Bedrock: {error_code}",
                error_code=error_code,
            ) from e

    def _build_request(self, user_message: str) -> dict[str, Any]:
        """Monta os parâmetros para a chamada converse.

        Estrutura (Design §8):
            modelId: BEDROCK_MODEL_ID
            system: [{"text": system_prompt}]
            messages: [{"role": "user", "content": [{"text": user_message}]}]
            inferenceConfig: {"maxTokens": ..., "temperature": ...}
        """
        return {
            "modelId": self._config.model_id,
            "system": [{"text": self._config.system_prompt}],
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": user_message}],
                }
            ],
            "inferenceConfig": {
                "maxTokens": self._config.max_tokens,
                "temperature": self._config.temperature,
            },
        }

    def _handle_client_error(
        self,
        error: ClientError,
        error_code: str,
        latency_ms: float,
        log_extra: dict[str, Any],
    ) -> None:
        """Classifica ClientError e lança exceção apropriada.

        Transitórios → retry (batchItemFailure):
            ThrottlingException, ServiceUnavailableException,
            ModelTimeoutException, InternalServerException

        Fatais → FAILED_FINAL:
            AccessDeniedException, ValidationException,
            ModelNotFoundException, outros
        """
        if error_code in _TRANSIENT_ERROR_CODES:
            category = "TRANSIENT"
            logger.warning(
                "Bedrock converse transient error",
                extra={
                    **log_extra,
                    "latency_ms": round(latency_ms, 1),
                    "error_code": error_code,
                    "error_category": category,
                },
            )
            raise BedrockTransientError(
                f"Erro transitório do Bedrock: {error_code}",
                error_code=error_code,
            ) from error

        # Fatal (inclui códigos conhecidos e desconhecidos)
        category = "FATAL"
        logger.warning(
            "Bedrock converse fatal error",
            extra={
                **log_extra,
                "latency_ms": round(latency_ms, 1),
                "error_code": error_code,
                "error_category": category,
            },
        )
        raise BedrockFatalError(
            f"Erro fatal do Bedrock: {error_code}",
            error_code=error_code,
        ) from error
