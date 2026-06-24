"""Testes para as tools MCP (lógica pura, sem servidor HTTP)."""

import pytest
from mcp_server.documents import DocumentStore
from mcp_server.tools import (
    get_support_procedure,
    health_check,
    search_support_documentation,
)


class TestSearchSupportDocumentation:
    """Testes da tool search_support_documentation."""

    def test_found_document(self, document_store: DocumentStore):
        """Deve retornar documento quando match é encontrado."""
        result = search_support_documentation(
            question="esqueci minha senha",
            document_store=document_store,
        )
        assert result["document_id"] == "DOC-001"
        assert result["confidence"] > 0
        assert result["demo"] is True
        assert result["answer"]
        assert result["document_title"]

    def test_not_found(self, document_store: DocumentStore):
        """Deve retornar fallback quando não há match."""
        result = search_support_documentation(
            question="previsão do tempo para amanhã",
            document_store=document_store,
        )
        assert result["document_id"] is None
        assert result["confidence"] == 0.0
        assert "atendente" in result["answer"].lower()
        assert result["demo"] is True

    def test_with_product_filter(self, document_store: DocumentStore):
        """Deve respeitar filtro de produto."""
        result = search_support_documentation(
            question="senha",
            product="Sistema Demo",
            document_store=document_store,
        )
        assert result["document_id"] == "DOC-001"

    def test_with_wrong_product(self, document_store: DocumentStore):
        """Deve retornar fallback se produto não corresponde."""
        result = search_support_documentation(
            question="senha",
            product="Produto Inexistente",
            document_store=document_store,
        )
        assert result["document_id"] is None

    def test_bloqueio(self, document_store: DocumentStore):
        """Busca por bloqueio deve retornar DOC-002."""
        result = search_support_documentation(
            question="minha conta foi bloqueada",
            document_store=document_store,
        )
        assert result["document_id"] == "DOC-002"

    def test_erro_acesso(self, document_store: DocumentStore):
        """Busca por erro de acesso deve retornar DOC-003."""
        result = search_support_documentation(
            question="erro ao acessar o sistema",
            document_store=document_store,
        )
        assert result["document_id"] == "DOC-003"

    def test_indisponibilidade(self, document_store: DocumentStore):
        """Busca por indisponibilidade deve retornar DOC-004."""
        result = search_support_documentation(
            question="sistema indisponível, fora do ar",
            document_store=document_store,
        )
        assert result["document_id"] == "DOC-004"

    def test_escalonamento(self, document_store: DocumentStore):
        """Busca por escalonamento deve retornar DOC-005."""
        result = search_support_documentation(
            question="preciso de escalonamento para segundo nível",
            document_store=document_store,
        )
        assert result["document_id"] == "DOC-005"


class TestGetSupportProcedure:
    """Testes da tool get_support_procedure."""

    def test_procedure_found(self, document_store: DocumentStore):
        """Deve retornar procedimento existente."""
        result = get_support_procedure(
            procedure_id="PROC-001",
            document_store=document_store,
        )
        assert result["procedure_id"] == "PROC-001"
        assert result["title"]
        assert len(result["steps"]) > 0
        assert result["demo"] is True

    def test_procedure_not_found(self, document_store: DocumentStore):
        """Deve retornar resposta vazia para procedimento inexistente."""
        result = get_support_procedure(
            procedure_id="PROC-999",
            document_store=document_store,
        )
        assert result["procedure_id"] == "PROC-999"
        assert result["title"] is None
        assert result["steps"] == []
        assert "não encontrado" in result["notes"][0].lower()
        assert result["demo"] is True

    def test_all_procedures_accessible(self, document_store: DocumentStore):
        """Todos os procedimentos cadastrados devem ser acessíveis."""
        for proc in document_store.procedures:
            result = get_support_procedure(
                procedure_id=proc.procedure_id,
                document_store=document_store,
            )
            assert result["procedure_id"] == proc.procedure_id
            assert result["title"] == proc.title


class TestHealthCheck:
    """Testes da tool health_check."""

    def test_healthy_response(self, document_store: DocumentStore):
        """Deve retornar status healthy."""
        result = health_check(document_store=document_store)
        assert result["status"] == "healthy"
        assert result["version"] == "1.0.0"
        assert result["documents_loaded"] == 5
        assert result["timestamp"]

    def test_empty_store(self):
        """Deve funcionar com store vazio."""
        empty_store = DocumentStore()
        result = health_check(document_store=empty_store)
        assert result["status"] == "healthy"
        assert result["documents_loaded"] == 0
