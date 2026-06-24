"""Testes para o módulo de documentos fictícios."""

import pytest
from mcp_server.documents import DocumentStore, SupportDocument, SupportProcedure


class TestDocumentStore:
    """Testes do carregamento e busca de documentos."""

    def test_load_documents(self, document_store: DocumentStore):
        """Deve carregar todos os 5 documentos fictícios."""
        assert document_store.document_count == 5

    def test_load_procedures(self, document_store: DocumentStore):
        """Deve carregar todos os procedimentos."""
        assert len(document_store.procedures) == 4

    def test_documents_have_required_fields(self, document_store: DocumentStore):
        """Cada documento deve ter os campos obrigatórios."""
        for doc in document_store.documents:
            assert doc.id
            assert doc.title
            assert doc.product
            assert doc.content
            assert doc.keywords
            assert doc.demo is True

    def test_procedures_have_required_fields(self, document_store: DocumentStore):
        """Cada procedimento deve ter os campos obrigatórios."""
        for proc in document_store.procedures:
            assert proc.procedure_id
            assert proc.title
            assert proc.steps
            assert proc.demo is True

    def test_search_by_keyword_senha(self, document_store: DocumentStore):
        """Busca por 'senha' deve retornar DOC-001."""
        result = document_store.search("como redefinir minha senha")
        assert result is not None
        assert result.id == "DOC-001"

    def test_search_by_keyword_bloqueio(self, document_store: DocumentStore):
        """Busca por 'bloqueio' deve retornar DOC-002."""
        result = document_store.search("minha conta está bloqueada")
        assert result is not None
        assert result.id == "DOC-002"

    def test_search_by_keyword_erro(self, document_store: DocumentStore):
        """Busca por 'erro acesso' deve retornar DOC-003."""
        result = document_store.search("estou com erro de acesso")
        assert result is not None
        assert result.id == "DOC-003"

    def test_search_by_keyword_indisponivel(self, document_store: DocumentStore):
        """Busca por 'indisponível' deve retornar DOC-004."""
        result = document_store.search("o sistema está indisponível")
        assert result is not None
        assert result.id == "DOC-004"

    def test_search_by_keyword_escalonamento(self, document_store: DocumentStore):
        """Busca por 'escalonamento' deve retornar DOC-005."""
        result = document_store.search("preciso de escalonamento")
        assert result is not None
        assert result.id == "DOC-005"

    def test_search_no_match(self, document_store: DocumentStore):
        """Busca sem match deve retornar None."""
        result = document_store.search("qual a previsão do tempo amanhã")
        assert result is None

    def test_search_with_product_filter(self, document_store: DocumentStore):
        """Busca com filtro de produto deve funcionar."""
        result = document_store.search("senha", product="Sistema Demo")
        assert result is not None
        assert result.id == "DOC-001"

    def test_search_with_wrong_product(self, document_store: DocumentStore):
        """Busca com produto inexistente deve retornar None."""
        result = document_store.search("senha", product="Outro Sistema")
        assert result is None

    def test_get_procedure_exists(self, document_store: DocumentStore):
        """Busca por procedimento existente deve retornar o correto."""
        proc = document_store.get_procedure("PROC-001")
        assert proc is not None
        assert proc.procedure_id == "PROC-001"
        assert len(proc.steps) > 0

    def test_get_procedure_not_found(self, document_store: DocumentStore):
        """Busca por procedimento inexistente deve retornar None."""
        proc = document_store.get_procedure("PROC-999")
        assert proc is None

    def test_load_from_empty_directory(self, tmp_path):
        """Carregar de diretório vazio deve retornar store vazio."""
        store = DocumentStore.load_from_directory(tmp_path)
        assert store.document_count == 0
        assert len(store.procedures) == 0

    def test_all_documents_have_demo_disclaimer(self, document_store: DocumentStore):
        """Todos os documentos devem ter aviso de demonstração."""
        for doc in document_store.documents:
            assert "fictício" in doc.content.lower() or "demonstração" in doc.content.lower()
