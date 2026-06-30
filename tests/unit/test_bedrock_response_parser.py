"""Testes unitários para src/shared/bedrock_client/response_parser.py."""

from __future__ import annotations

import pytest

from shared.bedrock_client.response_parser import FALLBACK_MESSAGE, extract_text_from_response


class TestSingleBlock:
    """Cenário: resposta com um único bloco de texto."""

    def test_single_text_block(self):
        response = {
            "output": {
                "message": {
                    "content": [{"text": "Olá! Como posso ajudar?"}]
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == "Olá! Como posso ajudar?"

    def test_preserves_exact_text(self):
        response = {
            "output": {
                "message": {
                    "content": [{"text": "  texto com espaços  "}]
                }
            }
        }
        # O texto original é preservado (não é stripped), mas blocos onde
        # strip() é vazio são rejeitados
        result = extract_text_from_response(response)
        assert result == "  texto com espaços  "


class TestMultipleBlocks:
    """Cenário: resposta com múltiplos blocos de texto."""

    def test_two_text_blocks(self):
        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": "Parte 1"},
                        {"text": "Parte 2"},
                    ]
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == "Parte 1\nParte 2"

    def test_three_text_blocks(self):
        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": "A"},
                        {"text": "B"},
                        {"text": "C"},
                    ]
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == "A\nB\nC"


class TestMixedBlocks:
    """Cenário: mix de blocos texto e não-texto."""

    def test_text_and_image(self):
        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": "Info"},
                        {"image": {"format": "png", "source": {}}},
                        {"text": "Mais"},
                    ]
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == "Info\nMais"

    def test_text_and_tool_use(self):
        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": "Resultado"},
                        {"toolUse": {"name": "search", "input": {}}},
                    ]
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == "Resultado"


class TestFallbackScenarios:
    """Cenários que devem retornar a mensagem de fallback."""

    def test_empty_content_list(self):
        response = {
            "output": {
                "message": {
                    "content": []
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == FALLBACK_MESSAGE

    def test_content_is_none(self):
        response = {
            "output": {
                "message": {
                    "content": None
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == FALLBACK_MESSAGE

    def test_content_absent(self):
        response = {
            "output": {
                "message": {}
            }
        }
        result = extract_text_from_response(response)
        assert result == FALLBACK_MESSAGE

    def test_only_non_text_blocks(self):
        response = {
            "output": {
                "message": {
                    "content": [
                        {"image": {"format": "png"}},
                        {"toolUse": {"name": "calc"}},
                    ]
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == FALLBACK_MESSAGE

    def test_text_blocks_with_empty_text(self):
        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": ""},
                        {"text": "   "},
                    ]
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == FALLBACK_MESSAGE

    def test_message_is_none(self):
        response = {"output": {"message": None}}
        result = extract_text_from_response(response)
        assert result == FALLBACK_MESSAGE

    def test_output_is_none(self):
        response = {"output": None}
        result = extract_text_from_response(response)
        assert result == FALLBACK_MESSAGE

    def test_empty_response(self):
        response = {}
        result = extract_text_from_response(response)
        assert result == FALLBACK_MESSAGE

    def test_text_is_none_in_block(self):
        response = {
            "output": {
                "message": {
                    "content": [{"text": None}]
                }
            }
        }
        result = extract_text_from_response(response)
        assert result == FALLBACK_MESSAGE


class TestFallbackMessage:
    """Verificação do conteúdo da mensagem de fallback."""

    def test_fallback_is_in_portuguese(self):
        assert "Desculpe" in FALLBACK_MESSAGE
        assert "reformular" in FALLBACK_MESSAGE
