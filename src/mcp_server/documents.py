"""
Carregamento e busca de documentos fictícios de suporte.

Os documentos são carregados de sample_documents/ em memória.
A busca é por palavras-chave simples (sem IA/LLM).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path


def _normalize(text: str) -> str:
    """Normaliza texto: minúsculas, sem acentos, sem pontuação, espaços únicos."""
    text = text.lower()
    # Remover acentos
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Remover pontuação
    text = re.sub(r"[^\w\s]", " ", text)
    # Normalizar espaços
    text = re.sub(r"\s+", " ", text).strip()
    return text


@dataclass
class SupportDocument:
    id: str
    title: str
    product: str
    language: str
    content: str
    keywords: list[str]
    procedures: list[str]
    updated_at: str
    demo: bool


@dataclass
class SupportProcedure:
    procedure_id: str
    title: str
    steps: list[str]
    notes: list[str]
    source: str
    demo: bool


@dataclass
class DocumentStore:
    """Armazena documentos e procedimentos fictícios em memória."""

    documents: list[SupportDocument] = field(default_factory=list)
    procedures: list[SupportProcedure] = field(default_factory=list)

    @classmethod
    def load_from_directory(cls, directory: Path | str) -> "DocumentStore":
        """Carrega documentos e procedimentos de um diretório."""
        directory = Path(directory)
        store = cls()

        docs_path = directory / "documents.json"
        if docs_path.exists():
            with open(docs_path, encoding="utf-8") as f:
                raw_docs = json.load(f)
            store.documents = [SupportDocument(**doc) for doc in raw_docs]

        procs_path = directory / "procedures.json"
        if procs_path.exists():
            with open(procs_path, encoding="utf-8") as f:
                raw_procs = json.load(f)
            store.procedures = [SupportProcedure(**proc) for proc in raw_procs]

        return store

    def search(self, question: str, product: str | None = None) -> SupportDocument | None:
        """
        Busca o documento mais relevante por palavras-chave.

        Lógica simples: conta quantas keywords do documento aparecem na pergunta.
        Tanto a pergunta quanto as keywords são normalizadas (sem acentos, lowercase, sem pontuação).
        Retorna o documento com maior score. Em empate, retorna o primeiro.
        """
        question_normalized = _normalize(question)
        best_doc: SupportDocument | None = None
        best_score = 0

        for doc in self.documents:
            if product and doc.product.lower() != product.lower():
                continue

            score = sum(1 for kw in doc.keywords if _normalize(kw) in question_normalized)
            if score > best_score:
                best_score = score
                best_doc = doc

        return best_doc

    def get_procedure(self, procedure_id: str) -> SupportProcedure | None:
        """Retorna um procedimento pelo ID."""
        for proc in self.procedures:
            if proc.procedure_id == procedure_id:
                return proc
        return None

    @property
    def document_count(self) -> int:
        return len(self.documents)
