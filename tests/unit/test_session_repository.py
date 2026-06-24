"""Testes do repositório de sessões DynamoDB."""

from __future__ import annotations

import time

import boto3
import pytest
from botocore.stub import Stubber

from integrator.exceptions import (
    DynamoDBFatalError,
    DynamoDBTransientError,
    SessionStatus,
)
from integrator.session_repository import SessionData, SessionRepository

TABLE_NAME = "test-sessions"


@pytest.fixture
def dynamodb_client():
    return boto3.client("dynamodb", region_name="us-east-1")


@pytest.fixture
def repo(dynamodb_client):
    return SessionRepository(
        dynamodb_client=dynamodb_client,
        table_name=TABLE_NAME,
        ttl_seconds=86400,
    )


def _sample_session_item() -> dict:
    """Item DynamoDB de sessão para testes."""
    return {
        "pk": {"S": "CONTACT#contact-001"},
        "contact_id": {"S": "contact-001"},
        "participant_id": {"S": "participant-001"},
        "participant_token_encrypted": {"B": b"encrypted-participant-token"},
        "connection_token_encrypted": {"B": b"encrypted-connection-token"},
        "connection_token_expiry": {"S": "2024-06-15T15:30:00Z"},
        "streaming_id": {"S": "streaming-001"},
        "status": {"S": "ACTIVE"},
        "created_at": {"S": "2024-06-15T14:30:00Z"},
        "updated_at": {"S": "2024-06-15T14:30:00Z"},
        "expires_at": {"N": str(int(time.time()) + 86400)},
        "last_message_id": {"S": "msg-001"},
        "handoff_requested": {"BOOL": False},
    }


class TestCreateSession:
    """Criação de sessão."""

    def test_create_success(self, dynamodb_client, repo):
        """Deve criar sessão com todos os campos."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("put_item", {})
            repo.create_session(
                contact_id="contact-001",
                participant_id="participant-001",
                participant_token_encrypted=b"token-enc",
                connection_token_encrypted=b"conn-enc",
                connection_token_expiry="2024-06-15T15:30:00Z",
                streaming_id="streaming-001",
            )

    def test_create_does_not_overwrite(self, dynamodb_client, repo):
        """Se sessão já existe, deve levantar ValueError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="ConditionalCheckFailedException",
            )
            with pytest.raises(ValueError, match="already exists"):
                repo.create_session(
                    contact_id="contact-001",
                    participant_id="participant-001",
                    participant_token_encrypted=b"token",
                    connection_token_encrypted=b"conn",
                    connection_token_expiry="2024-06-15T15:30:00Z",
                    streaming_id="streaming-001",
                )

    def test_create_transient_error(self, dynamodb_client, repo):
        """Throttling na criação deve levantar DynamoDBTransientError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="ThrottlingException",
            )
            with pytest.raises(DynamoDBTransientError):
                repo.create_session(
                    contact_id="contact-001",
                    participant_id="p",
                    participant_token_encrypted=b"t",
                    connection_token_encrypted=b"c",
                    connection_token_expiry="x",
                    streaming_id="s",
                )


class TestGetSession:
    """Leitura de sessão."""

    def test_get_existing(self, dynamodb_client, repo):
        """Sessão existente deve retornar SessionData populada."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("get_item", {"Item": _sample_session_item()})
            session = repo.get_session("contact-001")

        assert session is not None
        assert session.contact_id == "contact-001"
        assert session.participant_id == "participant-001"
        assert session.participant_token_encrypted == b"encrypted-participant-token"
        assert session.connection_token_encrypted == b"encrypted-connection-token"
        assert session.connection_token_expiry == "2024-06-15T15:30:00Z"
        assert session.status == SessionStatus.ACTIVE
        assert session.handoff_requested is False

    def test_get_not_found(self, dynamodb_client, repo):
        """Sessão inexistente deve retornar None."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("get_item", {})
            session = repo.get_session("nonexistent")

        assert session is None

    def test_get_transient_error(self, dynamodb_client, repo):
        """Erro transitório no GetItem deve propagar."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "get_item",
                service_error_code="InternalServerError",
            )
            with pytest.raises(DynamoDBTransientError):
                repo.get_session("contact-001")


class TestUpdateStatus:
    """Atualização de status."""

    def test_update_status(self, dynamodb_client, repo):
        """Deve atualizar status com sucesso e renovar TTL."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("update_item", {})
            repo.update_status("contact-001", SessionStatus.ACTIVE)

    def test_update_status_not_found(self, dynamodb_client, repo):
        """Update de item inexistente deve levantar ValueError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "update_item",
                service_error_code="ConditionalCheckFailedException",
            )
            with pytest.raises(ValueError, match="not found"):
                repo.update_status("nonexistent", SessionStatus.ACTIVE)

    def test_update_status_transient_error(self, dynamodb_client, repo):
        """Erro transitório deve propagar."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "update_item",
                service_error_code="ServiceUnavailable",
            )
            with pytest.raises(DynamoDBTransientError):
                repo.update_status("contact-001", SessionStatus.CLOSED)


class TestUpdateConnectionToken:
    """Renovação do ConnectionToken."""

    def test_update_token(self, dynamodb_client, repo):
        """Deve atualizar token e expiração."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("update_item", {})
            repo.update_connection_token(
                contact_id="contact-001",
                connection_token_encrypted=b"new-token-encrypted",
                connection_token_expiry="2024-06-15T16:30:00Z",
            )

    def test_update_token_not_found(self, dynamodb_client, repo):
        """Update de sessão inexistente deve levantar ValueError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "update_item",
                service_error_code="ConditionalCheckFailedException",
            )
            with pytest.raises(ValueError, match="not found"):
                repo.update_connection_token(
                    contact_id="nonexistent",
                    connection_token_encrypted=b"t",
                    connection_token_expiry="x",
                )


class TestMarkHandoff:
    """Transferência para atendente."""

    def test_mark_handoff(self, dynamodb_client, repo):
        """Deve marcar handoff com sucesso e renovar TTL."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("update_item", {})
            repo.mark_handoff("contact-001")

    def test_mark_handoff_not_found(self, dynamodb_client, repo):
        """Sessão inexistente deve levantar ValueError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "update_item",
                service_error_code="ConditionalCheckFailedException",
            )
            with pytest.raises(ValueError, match="not found"):
                repo.mark_handoff("nonexistent")


class TestTTLRenewal:
    """Verificar que TTL é renovado em updates."""

    def test_ttl_is_future(self, dynamodb_client, repo):
        """O expires_at calculado deve ser no futuro (now + ttl)."""
        now = int(time.time())
        expires = repo._new_expires_at()
        assert expires > now
        assert expires <= now + 86400 + 1  # tolerância de 1s


class TestFatalErrors:
    """Erros fatais do DynamoDB."""

    def test_resource_not_found(self, dynamodb_client, repo):
        """ResourceNotFoundException deve levantar DynamoDBFatalError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "get_item",
                service_error_code="ResourceNotFoundException",
            )
            with pytest.raises(DynamoDBFatalError):
                repo.get_session("contact-001")

    def test_validation_exception(self, dynamodb_client, repo):
        """ValidationException deve levantar DynamoDBFatalError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="ValidationException",
            )
            with pytest.raises(DynamoDBFatalError):
                repo.create_session(
                    contact_id="x",
                    participant_id="p",
                    participant_token_encrypted=b"t",
                    connection_token_encrypted=b"c",
                    connection_token_expiry="e",
                    streaming_id="s",
                )


class TestClientInjection:
    """Injeção do cliente DynamoDB."""

    def test_accepts_custom_client_and_table(self):
        """Deve aceitar cliente e nome de tabela customizados."""
        client = boto3.client("dynamodb", region_name="eu-west-1")
        repo = SessionRepository(dynamodb_client=client, table_name="my-table")
        assert repo._table_name == "my-table"
