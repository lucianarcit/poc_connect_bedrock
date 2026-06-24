"""Testes do motor do chat local."""

from __future__ import annotations

import pytest

from local_chat.chat_engine import (
    ChatResponse,
    format_response,
    is_exit_request,
    is_handoff_request,
    process_message,
)
from shared.mcp_client.exceptions import MCPConnectionError
from shared.mcp_client.models import ToolResult


class TestIsHandoffRequest:
    def test_falar_com_atendente(self):
        assert is_handoff_request("falar com atendente") is True

    def test_atendimento_humano(self):
        assert is_handoff_request("quero atendimento humano") is True

    def test_not_handoff(self):
        assert is_handoff_request("como redefinir senha") is False

    def test_case_insensitive(self):
        assert is_handoff_request("FALAR COM ATENDENTE") is True


class TestIsExitRequest:
    def test_sair(self):
        assert is_exit_request("sair") is True

    def test_exit(self):
        assert is_exit_request("exit") is True

    def test_quit(self):
        assert is_exit_request("quit") is True

    def test_not_exit(self):
        assert is_exit_request("ajuda") is False


class TestFormatResponse:
    def test_health_check(self):
        data = {"status": "healthy", "version": "1.0.0", "documents_loaded": 5, "timestamp": "T"}
        result = format_response("health_check", data)
        assert "healthy" in result
        assert "1.0.0" in result
        assert "5" in result

    def test_procedure(self):
        data = {
            "title": "Meu Proc",
            "steps": ["Passo 1", "Passo 2"],
            "notes": ["Nota"],
            "demo": True,
        }
        result = format_response("get_support_procedure", data)
        assert "Meu Proc" in result
        assert "1. Passo 1" in result
        assert "2. Passo 2" in result
        assert "Nota" in result
        assert "demonstração" in result.lower()

    def test_procedure_not_found(self):
        data = {"title": None, "steps": [], "notes": ["Não encontrado"], "demo": True}
        result = format_response("get_support_procedure", data)
        assert "não encontrado" in result.lower()

    def test_search_found(self):
        data = {
            "answer": "Faça isso e aquilo.",
            "document_title": "DOC Título",
            "document_id": "DOC-001",
            "demo": True,
        }
        result = format_response("search_support_documentation", data)
        assert "DOC Título (DOC-001)" in result
        assert "Faça isso e aquilo." in result
        assert "demonstração" in result.lower()

    def test_search_fallback(self):
        data = {"answer": "Não encontrei.", "document_title": None, "document_id": None, "demo": True}
        result = format_response("search_support_documentation", data)
        assert "Não encontrei." in result


class TestProcessMessage:
    def _mock_call_tool(self, name: str, args: dict) -> ToolResult:
        """Mock que retorna sucesso com dados simples."""
        return ToolResult(
            tool_name=name,
            success=True,
            data={"answer": "resposta mock", "document_id": "DOC-001", "document_title": "T", "demo": True},
            latency_ms=50.0,
        )

    def test_empty_message(self):
        resp = process_message("", self._mock_call_tool)
        assert resp.text == ""
        assert resp.is_exit is False

    def test_exit(self):
        resp = process_message("sair", self._mock_call_tool)
        assert resp.is_exit is True
        assert "logo" in resp.text.lower()

    def test_handoff(self):
        resp = process_message("falar com atendente", self._mock_call_tool)
        assert resp.is_handoff is True
        assert "atendente" in resp.text.lower()

    def test_normal_message(self):
        resp = process_message("como redefinir minha senha", self._mock_call_tool)
        assert resp.is_exit is False
        assert resp.is_handoff is False
        assert resp.tool_name == "search_support_documentation"
        assert "resposta mock" in resp.text

    def test_health_check_selection(self):
        resp = process_message("qual o status?", self._mock_call_tool)
        assert resp.tool_name == "health_check"

    def test_mcp_error(self):
        def failing_call(name, args):
            raise MCPConnectionError("Falha ao conectar")

        resp = process_message("senha", failing_call)
        assert resp.is_error is True
        assert "dificuldade" in resp.text.lower()

    def test_tool_returns_failure(self):
        def fail_result(name, args):
            return ToolResult(tool_name=name, success=False, error="timeout", latency_ms=100.0)

        resp = process_message("senha", fail_result)
        assert resp.is_error is True
        assert "erro" in resp.text.lower()
