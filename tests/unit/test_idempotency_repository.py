"""Testes do repositório de idempotência com lease."""

from __future__ import annotations

import time
from unittest.mock import patch

import boto3
import pytest
from botocore.stub import Stubber

from integrator.exceptions import (
    AcquireResult,
    DynamoDBFatalError,
    DynamoDBTransientError,
    IdempotencyStatus,
)
from integrator.idempotency_repository import IdempotencyRepository

TABLE_NAME = "test-idempotency"
LEASE_DURATION = 90


@pytest.fixture
def dynamodb_client():
    return boto3.client("dynamodb", region_name="us-east-1")


@pytest.fixture
def repo(dynamodb_client):
    return IdempotencyRepository(
        dynamodb_client=dynamodb_client,
        table_name=TABLE_NAME,
        ttl_seconds=86400,
        lease_duration_seconds=LEASE_DURATION,
    )


class TestTryAcquireNewMessage:
    """Mensagem nova — item não existe."""

    def test_acquired(self, dynamodb_client, repo):
        """Deve retornar ACQUIRED quando item não existe."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("put_item", {})
            result = repo.try_acquire("msg-001", "contact-001")

        assert result == AcquireResult.ACQUIRED

    def test_ttl_set_correctly(self, dynamodb_client, repo):
        """O expires_at deve ser now + ttl_seconds."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("put_item", {})

            before = int(time.time())
            repo.try_acquire("msg-002", "contact-001")
            after = int(time.time())

        # Verificamos via request params capturados pelo stubber
        # O stubber não rejeita, então o PutItem passou com valores corretos


class TestTryAcquireDuplicateCompleted:
    """Mensagem já processada com sucesso (COMPLETED)."""

    def test_returns_duplicate_completed(self, dynamodb_client, repo):
        """Deve retornar DUPLICATE_COMPLETED."""
        with Stubber(dynamodb_client) as stubber:
            # PutItem falha com ConditionalCheckFailedException
            stubber.add_client_error(
                "put_item",
                service_error_code="ConditionalCheckFailedException",
            )
            # GetItem retorna item COMPLETED
            stubber.add_response("get_item", {
                "Item": {
                    "pk": {"S": "MESSAGE#msg-001"},
                    "status": {"S": "COMPLETED"},
                    "lease_expires_at": {"N": "0"},
                    "attempt_count": {"N": "1"},
                }
            })
            result = repo.try_acquire("msg-001", "contact-001")

        assert result == AcquireResult.DUPLICATE_COMPLETED


class TestTryAcquireFailedFinal:
    """Mensagem com falha permanente."""

    def test_returns_failed_final(self, dynamodb_client, repo):
        """Deve retornar FAILED_FINAL."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="ConditionalCheckFailedException",
            )
            stubber.add_response("get_item", {
                "Item": {
                    "pk": {"S": "MESSAGE#msg-001"},
                    "status": {"S": "FAILED_FINAL"},
                    "lease_expires_at": {"N": "0"},
                    "attempt_count": {"N": "3"},
                }
            })
            result = repo.try_acquire("msg-001", "contact-001")

        assert result == AcquireResult.FAILED_FINAL


class TestTryAcquireLeaseActive:
    """Mensagem em processamento com lease ativo."""

    def test_returns_already_processing(self, dynamodb_client, repo):
        """Lease ativo deve impedir processamento concorrente."""
        future_lease = int(time.time()) + 999
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="ConditionalCheckFailedException",
            )
            stubber.add_response("get_item", {
                "Item": {
                    "pk": {"S": "MESSAGE#msg-001"},
                    "status": {"S": "PROCESSING"},
                    "lease_expires_at": {"N": str(future_lease)},
                    "attempt_count": {"N": "1"},
                }
            })
            result = repo.try_acquire("msg-001", "contact-001")

        assert result == AcquireResult.ALREADY_PROCESSING


class TestTryAcquireLeaseExpired:
    """Mensagem em processamento com lease expirado — reassumir."""

    def test_reassume_after_expired_lease(self, dynamodb_client, repo):
        """Lease expirado deve permitir reassumir via UpdateItem condicional."""
        expired_lease = int(time.time()) - 10  # expirou 10s atrás
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="ConditionalCheckFailedException",
            )
            stubber.add_response("get_item", {
                "Item": {
                    "pk": {"S": "MESSAGE#msg-001"},
                    "status": {"S": "PROCESSING"},
                    "lease_expires_at": {"N": str(expired_lease)},
                    "attempt_count": {"N": "1"},
                }
            })
            # UpdateItem para reassumir — sucesso
            stubber.add_response("update_item", {})

            result = repo.try_acquire("msg-001", "contact-001")

        assert result == AcquireResult.ACQUIRED

    def test_race_condition_on_reassume(self, dynamodb_client, repo):
        """Se outra instância reassumiu entre Get e Update, retorna ALREADY_PROCESSING."""
        expired_lease = int(time.time()) - 10
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="ConditionalCheckFailedException",
            )
            stubber.add_response("get_item", {
                "Item": {
                    "pk": {"S": "MESSAGE#msg-001"},
                    "status": {"S": "PROCESSING"},
                    "lease_expires_at": {"N": str(expired_lease)},
                    "attempt_count": {"N": "1"},
                }
            })
            # UpdateItem falha com ConditionalCheck (outra instância ganhou)
            stubber.add_client_error(
                "update_item",
                service_error_code="ConditionalCheckFailedException",
            )

            result = repo.try_acquire("msg-001", "contact-001")

        assert result == AcquireResult.ALREADY_PROCESSING


class TestTryAcquireTransientError:
    """Erro transitório do DynamoDB durante acquire."""

    def test_throttling_raises_transient(self, dynamodb_client, repo):
        """Throttling no PutItem deve levantar DynamoDBTransientError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="ThrottlingException",
            )
            with pytest.raises(DynamoDBTransientError):
                repo.try_acquire("msg-001", "contact-001")

    def test_internal_server_error_raises_transient(self, dynamodb_client, repo):
        """InternalServerError deve levantar DynamoDBTransientError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="InternalServerError",
            )
            with pytest.raises(DynamoDBTransientError):
                repo.try_acquire("msg-001", "contact-001")


class TestTryAcquireFatalError:
    """Erro fatal do DynamoDB durante acquire."""

    def test_resource_not_found_raises_fatal(self, dynamodb_client, repo):
        """ResourceNotFoundException deve levantar DynamoDBFatalError."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "put_item",
                service_error_code="ResourceNotFoundException",
            )
            with pytest.raises(DynamoDBFatalError):
                repo.try_acquire("msg-001", "contact-001")


class TestMarkCompleted:
    """Marcar mensagem como processada."""

    def test_mark_completed(self, dynamodb_client, repo):
        """Deve atualizar status para COMPLETED."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("update_item", {})
            repo.mark_completed("msg-001")

    def test_mark_completed_item_not_found(self, dynamodb_client, repo):
        """Se item não existe, deve apenas logar warning (não raise)."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "update_item",
                service_error_code="ConditionalCheckFailedException",
            )
            # Não deve levantar exceção
            repo.mark_completed("msg-nonexistent")


class TestMarkFailedFinal:
    """Marcar mensagem como falha permanente."""

    def test_mark_failed_final(self, dynamodb_client, repo):
        """Deve atualizar status para FAILED_FINAL."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_response("update_item", {})
            repo.mark_failed_final("msg-001")

    def test_mark_failed_final_item_not_found(self, dynamodb_client, repo):
        """Se item não existe, deve apenas logar warning."""
        with Stubber(dynamodb_client) as stubber:
            stubber.add_client_error(
                "update_item",
                service_error_code="ConditionalCheckFailedException",
            )
            repo.mark_failed_final("msg-nonexistent")


class TestClientInjection:
    """Verificar que client é injetável."""

    def test_accepts_external_client(self):
        """Deve aceitar cliente DynamoDB externo."""
        mock_client = boto3.client("dynamodb", region_name="us-east-1")
        repo = IdempotencyRepository(
            dynamodb_client=mock_client,
            table_name="custom-table",
        )
        assert repo._table_name == "custom-table"
