"""Fixtures compartilhadas para todos os testes."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Adicionar src/ ao path para que os imports funcionem nos testes
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture
def sample_documents_dir() -> Path:
    """Retorna o caminho do diretório de documentos fictícios."""
    return Path(__file__).resolve().parent.parent / "sample_documents"


@pytest.fixture
def document_store(sample_documents_dir):
    """Carrega o DocumentStore com os documentos fictícios."""
    from mcp_server.documents import DocumentStore

    return DocumentStore.load_from_directory(sample_documents_dir)
