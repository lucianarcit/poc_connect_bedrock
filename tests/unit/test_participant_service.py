"""Testes do cliente Amazon Connect Participant Service."""

from __future__ import annotations

import boto3
import pytest
from botocore.stub import Stubber

from integrator.exceptions import ErrorCategory
from integrator.participant_service import (
    DEFAULT_MAX_MESSAGE_BYTES,
    DisconnectResult,
    ParticipantService,
    RenewConnectionResult,
    SendMessageResult,
    SentMessageInfo,
    generate_client_token,
    split_content_by_bytes,
)


@pytest.fixture
def cp_client():
    return boto3.client("connectparticipant", region_name="us-east-1")


@pytest.fixture
def service(cp_client):
    return ParticipantService(
        connectparticipant_client=cp_client,
        max_retries=1,
    )


# --- split_content_by_bytes ---


class TestSplitContentByBytes:
    def test_short_ascii(self):
        """Conteúdo curto ASCII não deve ser dividido."""
        result = split_content_by_bytes("hello", max_bytes=100)
        assert result == ["hello"]

    def test_exact_limit(self):
        """Conteúdo exatamente no limite não deve ser dividido."""
        content = "a" * 100
        result = split_content_by_bytes(content, max_bytes=100)
        assert result == [content]

    def test_over_limit_ascii(self):
        """Conteúdo ASCII acima do limite deve ser dividido."""
        content = "a" * 200
        result = split_content_by_bytes(content, max_bytes=100)
        assert len(result) >= 2
        # Reconstruir deve dar o original
        assert "".join(result) == content

    def test_utf8_multibyte_accents(self):
        """Caracteres acentuados (2 bytes UTF-8) devem ser contados corretamente."""
        # 'á' = 2 bytes em UTF-8
        content = "á" * 100  # 200 bytes
        result = split_content_by_bytes(content, max_bytes=100)
        assert len(result) >= 2
        assert "".join(result) == content

    def test_utf8_emoji(self):
        """Emoji (4 bytes UTF-8) devem ser contados corretamente."""
        # '🔥' = 4 bytes em UTF-8
        content = "🔥" * 50  # 200 bytes
        result = split_content_by_bytes(content, max_bytes=100)
        assert len(result) >= 2
        assert "".join(result) == content

    def test_no_split_mid_character(self):
        """Nunca deve cortar no meio de um caractere multibyte."""
        content = "a" * 99 + "á"  # 101 bytes total
        result = split_content_by_bytes(content, max_bytes=100)
        # Deve ter cortado antes do 'á'
        for chunk in result:
            # Cada chunk deve ser válido UTF-8 (se não fosse, decodificação falharia)
            chunk.encode("utf-8")

    def test_prefers_newline_split(self):
        """Deve preferir cortar em quebra de linha."""
        line1 = "a" * 70
        line2 = "b" * 20
        content = line1 + "\n" + line2  # 91 chars/bytes
        result = split_content_by_bytes(content, max_bytes=85)
        assert result[0].endswith("\n")

    def test_mixed_content(self):
        """Conteúdo misto (ASCII + acentos + emoji) deve dividir corretamente."""
        content = "Olá mundo! 🌍 " * 100  # ~1800 bytes
        result = split_content_by_bytes(content, max_bytes=500)
        assert len(result) >= 3
        assert "".join(result) == content

    def test_real_limit_15000(self):
        """Conteúdo abaixo de 15000 bytes não deve ser dividido."""
        content = "x" * 14999
        result = split_content_by_bytes(content, max_bytes=DEFAULT_MAX_MESSAGE_BYTES)
        assert len(result) == 1


# --- generate_client_token ---


class TestGenerateClientToken:
    def test_deterministic(self):
        """Mesmo input deve gerar mesmo token."""
        t1 = generate_client_token("c1", "m1", 0)
        t2 = generate_client_token("c1", "m1", 0)
        assert t1 == t2

    def test_different_source_message_id(self):
        """Mesma resposta para source_message_id diferente deve gerar tokens diferentes."""
        t1 = generate_client_token("contact-1", "msg-001", 0)
        t2 = generate_client_token("contact-1", "msg-002", 0)
        assert t1 != t2

    def test_different_chunk_index(self):
        """Chunk index diferente deve gerar tokens diferentes."""
        t1 = generate_client_token("c1", "m1", 0)
        t2 = generate_client_token("c1", "m1", 1)
        assert t1 != t2

    def test_retry_same_message_same_tokens(self):
        """Retry da mesma mensagem deve gerar os mesmos tokens."""
        # Simula 2 tentativas da mesma mensagem
        tokens_attempt1 = [generate_client_token("c1", "m1", i) for i in range(3)]
        tokens_attempt2 = [generate_client_token("c1", "m1", i) for i in range(3)]
        assert tokens_attempt1 == tokens_attempt2

    def test_length(self):
        """Token deve ter 64 caracteres hex."""
        token = generate_client_token("c", "m", 0)
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)


# --- SendMessage ---


class TestSendMessage:
    def test_success_single_chunk(self, cp_client, service):
        """Mensagem curta enviada com sucesso."""
        with Stubber(cp_client) as stubber:
            stubber.add_response("send_message", {
                "Id": "resp-msg-001",
                "AbsoluteTime": "2024-06-15T14:30:00Z",
            })
            result = service.send_message(
                connection_token="fake-token",
                content="Olá!",
                contact_id="contact-001",
                source_message_id="src-msg-001",
            )

        assert result.success is True
        assert len(result.messages_sent) == 1
        assert result.messages_sent[0].message_id == "resp-msg-001"
        assert result.messages_sent[0].absolute_time == "2024-06-15T14:30:00Z"

    def test_success_multiple_chunks(self, cp_client, service):
        """Mensagem longa dividida em chunks, todos enviados com sucesso."""
        svc = ParticipantService(cp_client, max_message_bytes=50, max_retries=0)
        content = "a" * 120  # 3 chunks de ~50 bytes

        with Stubber(cp_client) as stubber:
            for i in range(3):
                stubber.add_response("send_message", {
                    "Id": f"resp-{i}",
                    "AbsoluteTime": f"2024-06-15T14:3{i}:00Z",
                })
            result = svc.send_message(
                connection_token="t",
                content=content,
                contact_id="c1",
                source_message_id="m1",
            )

        assert result.success is True
        assert len(result.messages_sent) == 3

    def test_expired_token(self, cp_client, service):
        """ExpiredTokenException deve retornar TRANSIENT (permite renovação)."""
        with Stubber(cp_client) as stubber:
            stubber.add_client_error(
                "send_message",
                service_error_code="ExpiredTokenException",
                service_message="Token expired",
            )
            stubber.add_client_error(
                "send_message",
                service_error_code="ExpiredTokenException",
                service_message="Token expired",
            )
            result = service.send_message(
                connection_token="expired-token",
                content="hello",
                contact_id="c1",
                source_message_id="m1",
            )

        assert result.success is False
        assert result.error_category == ErrorCategory.TRANSIENT
        assert "TOKEN_EXPIRED" in result.error

    def test_access_denied_is_fatal(self, cp_client, service):
        """AccessDeniedException deve retornar FATAL (não é expiração)."""
        with Stubber(cp_client) as stubber:
            stubber.add_client_error(
                "send_message",
                service_error_code="AccessDeniedException",
                service_message="Not authorized",
            )
            result = service.send_message(
                connection_token="bad-token",
                content="hello",
                contact_id="c1",
                source_message_id="m1",
            )

        assert result.success is False
        assert result.error_category == ErrorCategory.FATAL
        assert "AUTHORIZATION_ERROR" in result.error

    def test_throttling_with_retry(self, cp_client, service):
        """ThrottlingException deve fazer retry e retornar TRANSIENT se esgotar."""
        with Stubber(cp_client) as stubber:
            stubber.add_client_error("send_message", service_error_code="ThrottlingException")
            stubber.add_client_error("send_message", service_error_code="ThrottlingException")
            result = service.send_message(
                connection_token="t",
                content="hello",
                contact_id="c1",
                source_message_id="m1",
            )

        assert result.success is False
        assert result.error_category == ErrorCategory.TRANSIENT

    def test_validation_exception_fatal(self, cp_client, service):
        """ValidationException deve retornar FATAL sem retry."""
        with Stubber(cp_client) as stubber:
            stubber.add_client_error("send_message", service_error_code="ValidationException")
            result = service.send_message(
                connection_token="t",
                content="hello",
                contact_id="c1",
                source_message_id="m1",
            )

        assert result.success is False
        assert result.error_category == ErrorCategory.FATAL

    def test_failure_on_second_chunk(self, cp_client):
        """Falha no segundo chunk deve retornar primeiro chunk em messages_sent."""
        svc = ParticipantService(cp_client, max_message_bytes=50, max_retries=0)
        content = "a" * 120  # 3 chunks

        with Stubber(cp_client) as stubber:
            stubber.add_response("send_message", {
                "Id": "resp-0", "AbsoluteTime": "T0",
            })
            stubber.add_client_error("send_message", service_error_code="ExpiredTokenException")

            result = svc.send_message(
                connection_token="t",
                content=content,
                contact_id="c1",
                source_message_id="m1",
            )

        assert result.success is False
        assert len(result.messages_sent) == 1
        assert result.messages_sent[0].message_id == "resp-0"
        assert result.failed_chunk_index == 1


# --- DisconnectParticipant ---


class TestDisconnectParticipant:
    def test_success(self, cp_client, service):
        """Desconexão com sucesso."""
        with Stubber(cp_client) as stubber:
            stubber.add_response("disconnect_participant", {})
            result = service.disconnect_participant("fake-token")

        assert result.success is True
        assert result.error is None

    def test_transient_error(self, cp_client, service):
        """Erro transitório na desconexão deve retornar resultado estruturado."""
        with Stubber(cp_client) as stubber:
            stubber.add_client_error(
                "disconnect_participant",
                service_error_code="InternalServerError",
            )
            result = service.disconnect_participant("fake-token")

        assert result.success is False
        assert result.error_category == ErrorCategory.TRANSIENT

    def test_fatal_error(self, cp_client, service):
        """Erro fatal na desconexão deve retornar FATAL."""
        with Stubber(cp_client) as stubber:
            stubber.add_client_error(
                "disconnect_participant",
                service_error_code="AccessDeniedException",
            )
            result = service.disconnect_participant("bad-token")

        assert result.success is False
        assert result.error_category == ErrorCategory.FATAL


# --- RenewConnection ---


class TestRenewConnection:
    def test_success(self, cp_client, service):
        """Renovação com sucesso retorna novo token e expiração."""
        with Stubber(cp_client) as stubber:
            stubber.add_response("create_participant_connection", {
                "ConnectionCredentials": {
                    "ConnectionToken": "new-token-abc",
                    "Expiry": "2024-06-15T16:30:00Z",
                },
            })
            result = service.renew_connection("participant-token")

        assert result.success is True
        assert result.connection_token == "new-token-abc"
        assert result.expiry == "2024-06-15T16:30:00Z"

    def test_expired_token(self, cp_client, service):
        """ExpiredTokenException na renovação → TRANSIENT (retry)."""
        with Stubber(cp_client) as stubber:
            stubber.add_client_error(
                "create_participant_connection",
                service_error_code="ExpiredTokenException",
            )
            stubber.add_client_error(
                "create_participant_connection",
                service_error_code="ExpiredTokenException",
            )
            result = service.renew_connection("expired-participant-token")

        assert result.success is False
        assert result.error_category == ErrorCategory.TRANSIENT

    def test_access_denied_fatal(self, cp_client, service):
        """AccessDeniedException na renovação → FATAL (contato encerrado)."""
        with Stubber(cp_client) as stubber:
            stubber.add_client_error(
                "create_participant_connection",
                service_error_code="AccessDeniedException",
            )
            result = service.renew_connection("invalid-token")

        assert result.success is False
        assert result.error_category == ErrorCategory.FATAL

    def test_throttling_retry(self, cp_client, service):
        """Throttling deve fazer retry e então sucesso."""
        with Stubber(cp_client) as stubber:
            stubber.add_client_error(
                "create_participant_connection",
                service_error_code="ThrottlingException",
            )
            stubber.add_response("create_participant_connection", {
                "ConnectionCredentials": {
                    "ConnectionToken": "renewed",
                    "Expiry": "2024-06-15T17:00:00Z",
                },
            })
            result = service.renew_connection("participant-token")

        assert result.success is True
        assert result.connection_token == "renewed"


# --- Injeção de client ---


class TestClientInjection:
    def test_accepts_external_client(self):
        """Deve aceitar client boto3 externo."""
        client = boto3.client("connectparticipant", region_name="eu-west-1")
        svc = ParticipantService(connectparticipant_client=client)
        assert svc._client is client
