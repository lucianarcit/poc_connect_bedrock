"""Configuração do Integrator — variáveis de ambiente e constantes."""

from __future__ import annotations

import os


def get_sessions_table_name() -> str:
    return os.environ.get("SESSIONS_TABLE_NAME", "connect-mcp-poc-sessions")


def get_idempotency_table_name() -> str:
    return os.environ.get("IDEMPOTENCY_TABLE_NAME", "connect-mcp-poc-idempotency")


def get_session_ttl_seconds() -> int:
    """TTL padrão para sessões: 24 horas."""
    return int(os.environ.get("SESSION_TTL_SECONDS", "86400"))


def get_idempotency_ttl_seconds() -> int:
    """TTL padrão para idempotência: 24 horas."""
    return int(os.environ.get("IDEMPOTENCY_TTL_SECONDS", "86400"))


def get_lease_duration_seconds() -> int:
    """Duração do lease de processamento: 90 segundos (> Lambda timeout 60s)."""
    return int(os.environ.get("LEASE_DURATION_SECONDS", "90"))


def get_sqs_visibility_timeout() -> int:
    """SQS VisibilityTimeout: 360 segundos (6x Lambda timeout, recomendação AWS)."""
    return int(os.environ.get("SQS_VISIBILITY_TIMEOUT", "360"))
