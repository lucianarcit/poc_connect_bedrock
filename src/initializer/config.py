"""Configuração da Lambda Initializer."""

from __future__ import annotations

import os


def get_sns_topic_arn() -> str:
    return os.environ.get("SNS_TOPIC_ARN", "")


def get_kms_key_id() -> str:
    return os.environ.get("KMS_KEY_ID", "")


def get_sessions_table_name() -> str:
    return os.environ.get("SESSIONS_TABLE_NAME", "connect-mcp-poc-sessions")


def get_initialization_lease_seconds() -> int:
    """Lease para reserva de inicialização (padrão: 15s, execução deve completar em <4s)."""
    return int(os.environ.get("INITIALIZATION_LEASE_SECONDS", "15"))
