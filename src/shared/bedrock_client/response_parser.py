"""Parser de resposta da Amazon Bedrock Converse API.

Responsável por extrair texto da resposta do modelo, lidando com:
- Resposta com um único bloco de texto
- Resposta com múltiplos blocos de texto (concatenação com \\n)
- Resposta com blocos não-texto (ignorados)
- Resposta vazia ou ausente (retorna fallback)
"""

from __future__ import annotations

# Mensagem de fallback quando o modelo não gera texto válido (Requisito 3.3)
FALLBACK_MESSAGE = (
    "Desculpe, não consegui gerar uma resposta. "
    "Por favor, tente reformular sua pergunta."
)


def extract_text_from_response(response: dict) -> str:
    """Extrai texto da resposta da Converse API.

    Algoritmo (Design §9):
    1. Localizar output.message.content na resposta
    2. Se content é None ou lista vazia → retornar FALLBACK_MESSAGE
    3. Filtrar blocos que possuem chave "text"
    4. Remover blocos onde text é None ou string vazia/whitespace
    5. Coletar valores .text dos blocos restantes
    6. Se nenhum bloco válido → retornar FALLBACK_MESSAGE
    7. Concatenar com "\\n" e retornar

    Args:
        response: Dicionário da resposta completa da Converse API.

    Returns:
        Texto extraído ou mensagem de fallback.
    """
    # 1. Localizar output.message.content
    output = response.get("output")
    if not output or not isinstance(output, dict):
        return FALLBACK_MESSAGE

    message = output.get("message")
    if not message or not isinstance(message, dict):
        return FALLBACK_MESSAGE

    content = message.get("content")

    # 2. Se content é None ou lista vazia
    if not content or not isinstance(content, list):
        return FALLBACK_MESSAGE

    # 3-5. Filtrar blocos com "text" não vazio
    text_values: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if text is None:
            continue
        if not isinstance(text, str):
            continue
        stripped = text.strip()
        if not stripped:
            continue
        text_values.append(text)

    # 6. Se nenhum bloco válido
    if not text_values:
        return FALLBACK_MESSAGE

    # 7. Concatenar com "\n"
    return "\n".join(text_values)
