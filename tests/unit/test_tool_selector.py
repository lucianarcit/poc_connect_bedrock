"""Testes para o seletor determinístico de tools."""

import pytest
from shared.mcp_client.tool_selector import ToolSelector


class TestToolSelector:
    """Testes da seleção de tools por palavras-chave."""

    @pytest.fixture
    def selector(self) -> ToolSelector:
        return ToolSelector()

    # --- health_check ---

    def test_select_health_check_saude(self, selector: ToolSelector):
        assert selector.select_tool("qual o status de saúde?") == "health_check"

    def test_select_health_check_status(self, selector: ToolSelector):
        assert selector.select_tool("status do sistema") == "health_check"

    def test_select_health_check_disponivel(self, selector: ToolSelector):
        assert selector.select_tool("o servidor está disponível?") == "health_check"

    def test_select_health_check_ping(self, selector: ToolSelector):
        assert selector.select_tool("ping") == "health_check"

    # --- get_support_procedure ---

    def test_select_procedure_keyword(self, selector: ToolSelector):
        assert selector.select_tool("qual o procedimento?") == "get_support_procedure"

    def test_select_procedure_proc_id(self, selector: ToolSelector):
        assert selector.select_tool("me mostra o PROC-002") == "get_support_procedure"

    def test_select_procedure_passo_a_passo(self, selector: ToolSelector):
        assert selector.select_tool("passo a passo para desbloquear") == "get_support_procedure"

    def test_select_procedure_etapas(self, selector: ToolSelector):
        assert selector.select_tool("quais as etapas?") == "get_support_procedure"

    # --- search_support_documentation (fallback) ---

    def test_select_search_password(self, selector: ToolSelector):
        assert selector.select_tool("como redefinir minha senha?") == "search_support_documentation"

    def test_select_search_generic(self, selector: ToolSelector):
        assert selector.select_tool("preciso de ajuda") == "search_support_documentation"

    def test_select_search_unknown(self, selector: ToolSelector):
        assert selector.select_tool("xpto abc 123") == "search_support_documentation"

    # --- build_arguments ---

    def test_build_args_health_check(self, selector: ToolSelector):
        args = selector.build_arguments("health_check", "status")
        assert args == {}

    def test_build_args_search(self, selector: ToolSelector):
        args = selector.build_arguments("search_support_documentation", "como trocar senha")
        assert args == {"question": "como trocar senha"}

    def test_build_args_procedure_with_id(self, selector: ToolSelector):
        args = selector.build_arguments("get_support_procedure", "mostra PROC-003")
        assert args == {"procedure_id": "PROC-003"}

    def test_build_args_procedure_without_id(self, selector: ToolSelector):
        """Sem ID explícito, deve retornar PROC-001 como padrão."""
        args = selector.build_arguments("get_support_procedure", "qual o procedimento?")
        assert args == {"procedure_id": "PROC-001"}

    def test_build_args_procedure_lowercase_id(self, selector: ToolSelector):
        """ID em lowercase deve ser normalizado para uppercase."""
        args = selector.build_arguments("get_support_procedure", "proc-002 por favor")
        assert args == {"procedure_id": "PROC-002"}

    # --- Caso de borda ---

    def test_empty_message_returns_default(self, selector: ToolSelector):
        assert selector.select_tool("") == "search_support_documentation"

    def test_custom_keywords(self):
        """Deve aceitar keywords customizadas."""
        custom = ToolSelector(
            tool_keywords={"my_tool": ["magic", "abracadabra"]},
            default_tool="fallback",
        )
        assert custom.select_tool("use magic") == "my_tool"
        assert custom.select_tool("hello") == "fallback"
