"""
Configuração de logging JSON estruturado para as Lambdas.

Garante que campos em `extra` são serializados como campos de primeiro nível
no JSON de log, permitindo CloudWatch Metric Filters como {"metric": "FailedFinal"}.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formatter que produz logs como objetos JSON com campos extras de primeiro nível."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Adicionar campos de 'extra' como campos de primeiro nível
        # Excluir campos padrão do LogRecord
        standard_attrs = {
            "name", "msg", "args", "created", "relativeCreated", "thread",
            "threadName", "msecs", "filename", "funcName", "levelno",
            "lineno", "module", "exc_info", "exc_text", "stack_info",
            "pathname", "processName", "process", "message", "levelname",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                log_entry[key] = value

        return json.dumps(log_entry, default=str, ensure_ascii=False)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Configura o root logger com JSONFormatter."""
    root = logging.getLogger()
    root.setLevel(level)

    # Remover handlers existentes
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)
