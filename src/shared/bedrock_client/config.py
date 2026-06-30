"""Configuração do BedrockClient — leitura e validação de variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass

from shared.bedrock_client.exceptions import BedrockConfigurationError

# System prompt padrão com as 5 instruções obrigatórias (Requisito 4)
DEFAULT_SYSTEM_PROMPT = (
    "Você é um agente virtual de suporte. "
    "Responda sempre em português brasileiro. "
    "Seja claro e objetivo nas respostas. "
    "Atue como agente virtual de suporte. "
    "Não invente informações que não estejam disponíveis. "
    "Informe ao usuário quando não tiver dados suficientes para responder."
)


@dataclass(frozen=True)
class BedrockConfig:
    """Configuração validada do BedrockClient.

    Todos os valores são validados na construção. Se inválidos,
    BedrockConfigurationError é lançado.
    """

    model_id: str
    max_tokens: int
    temperature: float
    system_prompt: str
    timeout_seconds: int
    region: str


def load_config() -> BedrockConfig:
    """Lê variáveis de ambiente e retorna configuração validada.

    Raises:
        BedrockConfigurationError: Se BEDROCK_MODEL_ID ausente/vazia ou
            valores numéricos fora dos ranges permitidos.
    """
    # BEDROCK_MODEL_ID — obrigatória, não vazia
    model_id = os.environ.get("BEDROCK_MODEL_ID", "").strip()
    if not model_id:
        raise BedrockConfigurationError(
            "BEDROCK_MODEL_ID não definida ou vazia. "
            "Configure a variável de ambiente com um model ID válido.",
            error_code="MISSING_MODEL_ID",
        )

    # BEDROCK_MAX_TOKENS — padrão 1024, range [1, 4096]
    max_tokens_raw = os.environ.get("BEDROCK_MAX_TOKENS", "1024")
    try:
        max_tokens = int(max_tokens_raw)
    except ValueError:
        raise BedrockConfigurationError(
            f"BEDROCK_MAX_TOKENS deve ser inteiro, recebido: '{max_tokens_raw}'",
            error_code="INVALID_MAX_TOKENS",
        )
    if not (1 <= max_tokens <= 4096):
        raise BedrockConfigurationError(
            f"BEDROCK_MAX_TOKENS deve estar entre 1 e 4096, recebido: {max_tokens}",
            error_code="INVALID_MAX_TOKENS",
        )

    # BEDROCK_TEMPERATURE — padrão 0.7, range [0.0, 1.0]
    temperature_raw = os.environ.get("BEDROCK_TEMPERATURE", "0.7")
    try:
        temperature = float(temperature_raw)
    except ValueError:
        raise BedrockConfigurationError(
            f"BEDROCK_TEMPERATURE deve ser decimal, recebido: '{temperature_raw}'",
            error_code="INVALID_TEMPERATURE",
        )
    if not (0.0 <= temperature <= 1.0):
        raise BedrockConfigurationError(
            f"BEDROCK_TEMPERATURE deve estar entre 0.0 e 1.0, recebido: {temperature}",
            error_code="INVALID_TEMPERATURE",
        )

    # BEDROCK_SYSTEM_PROMPT — padrão com instruções em pt-BR
    system_prompt_raw = os.environ.get("BEDROCK_SYSTEM_PROMPT", "").strip()
    system_prompt = system_prompt_raw if system_prompt_raw else DEFAULT_SYSTEM_PROMPT

    # BEDROCK_TIMEOUT_SECONDS — padrão 20, range [5, ∞)
    timeout_raw = os.environ.get("BEDROCK_TIMEOUT_SECONDS", "20")
    try:
        timeout_seconds = int(timeout_raw)
    except ValueError:
        raise BedrockConfigurationError(
            f"BEDROCK_TIMEOUT_SECONDS deve ser inteiro, recebido: '{timeout_raw}'",
            error_code="INVALID_TIMEOUT",
        )
    if timeout_seconds < 5:
        raise BedrockConfigurationError(
            f"BEDROCK_TIMEOUT_SECONDS deve ser >= 5, recebido: {timeout_seconds}",
            error_code="INVALID_TIMEOUT",
        )

    # AWS_REGION — padrão us-east-1
    region = os.environ.get("AWS_REGION", "us-east-1")

    return BedrockConfig(
        model_id=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system_prompt,
        timeout_seconds=timeout_seconds,
        region=region,
    )
