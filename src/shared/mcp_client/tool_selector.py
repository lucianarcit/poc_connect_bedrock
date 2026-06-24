"""
Seletor determinístico de tools MCP por palavras-chave.

Decisão explícita: NÃO há IA, LLM, Bedrock ou raciocínio.
A seleção é um mapeamento estático de keywords para tool names.

Preparado para futura substituição por:
- Amazon Bedrock (classificação por LLM)
- Roteador baseado em embeddings
- MCP real do cliente
"""

from __future__ import annotations


# Mapeamento: tool_name → lista de keywords que ativam essa tool
_TOOL_KEYWORDS: dict[str, list[str]] = {
    "health_check": [
        "saúde",
        "status",
        "disponível",
        "health",
        "ping",
        "funcionando",
    ],
    "get_support_procedure": [
        "procedimento",
        "proc-",
        "passo a passo",
        "etapas",
        "como fazer",
        "passos",
    ],
    # search_support_documentation é o fallback (sem keywords específicas)
}

_DEFAULT_TOOL = "search_support_documentation"


class ToolSelector:
    """
    Seleciona a tool MCP adequada com base em palavras-chave na mensagem.

    Interface simples para permitir substituição futura.
    """

    def __init__(
        self,
        tool_keywords: dict[str, list[str]] | None = None,
        default_tool: str = _DEFAULT_TOOL,
    ) -> None:
        self._tool_keywords = tool_keywords or _TOOL_KEYWORDS
        self._default_tool = default_tool

    def select_tool(self, message: str) -> str:
        """
        Seleciona a tool mais adequada para a mensagem.

        Args:
            message: Texto da mensagem do usuário.

        Returns:
            Nome da tool MCP a ser chamada.
        """
        message_lower = message.lower()

        for tool_name, keywords in self._tool_keywords.items():
            for keyword in keywords:
                if keyword.lower() in message_lower:
                    return tool_name

        return self._default_tool

    def build_arguments(self, tool_name: str, message: str) -> dict:
        """
        Constrói os argumentos para a tool selecionada.

        Args:
            tool_name: Nome da tool MCP.
            message: Mensagem original do usuário.

        Returns:
            Dict com os argumentos para call_tool.
        """
        if tool_name == "health_check":
            return {}
        elif tool_name == "get_support_procedure":
            # Tentar extrair PROC-XXX da mensagem
            procedure_id = self._extract_procedure_id(message)
            return {"procedure_id": procedure_id}
        else:
            # search_support_documentation
            return {"question": message}

    @staticmethod
    def _extract_procedure_id(message: str) -> str:
        """Extrai o ID do procedimento da mensagem, ou retorna padrão."""
        import re

        match = re.search(r"PROC-\d+", message, re.IGNORECASE)
        if match:
            return match.group(0).upper()
        return "PROC-001"
