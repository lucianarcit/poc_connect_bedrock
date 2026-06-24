"""
Fakes para testes de integração local — sem boto3 real.

Implementa repositórios e ParticipantService em memória.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from integrator.exceptions import (
    AcquireResult,
    DynamoDBTransientError,
    ErrorCategory,
    IdempotencyStatus,
    SessionStatus,
)
from integrator.models import ConnectChatMessage
from integrator.participant_service import (
    RenewConnectionResult,
    SendMessageResult,
    SentMessageInfo,
)
from integrator.session_repository import SessionData
from shared.crypto import FakeCryptoService


class FakeSessionRepository:
    """Repositório de sessões em memória."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionData] = {}

    def seed(self, session: SessionData) -> None:
        """Insere sessão para testes."""
        self._sessions[session.contact_id] = session

    def get_session(self, contact_id: str) -> SessionData | None:
        return self._sessions.get(contact_id)

    def update_connection_token(
        self, contact_id: str, connection_token_encrypted: bytes, connection_token_expiry: str
    ) -> None:
        session = self._sessions.get(contact_id)
        if session is None:
            raise ValueError(f"Session not found: {contact_id}")
        # Dataclass não é frozen no repo real, mas SessionData é frozen
        # Substituir por nova instância
        self._sessions[contact_id] = SessionData(
            contact_id=session.contact_id,
            participant_id=session.participant_id,
            participant_token_encrypted=session.participant_token_encrypted,
            connection_token_encrypted=connection_token_encrypted,
            connection_token_expiry=connection_token_expiry,
            streaming_id=session.streaming_id,
            status=session.status,
            created_at=session.created_at,
            updated_at=session.updated_at,
            expires_at=session.expires_at,
            last_message_id=session.last_message_id,
            handoff_requested=session.handoff_requested,
        )


class FakeIdempotencyRepository:
    """Repositório de idempotência em memória com lease."""

    def __init__(self, lease_duration: int = 90) -> None:
        self._items: dict[str, dict] = {}
        self._lease_duration = lease_duration

    def try_acquire(self, message_id: str, contact_id: str) -> AcquireResult:
        key = f"MESSAGE#{message_id}"
        now = int(time.time())

        if key not in self._items:
            self._items[key] = {
                "status": IdempotencyStatus.PROCESSING.value,
                "lease_expires_at": now + self._lease_duration,
                "contact_id": contact_id,
            }
            return AcquireResult.ACQUIRED

        item = self._items[key]
        status = item["status"]

        if status == IdempotencyStatus.COMPLETED.value:
            return AcquireResult.DUPLICATE_COMPLETED
        if status == IdempotencyStatus.FAILED_FINAL.value:
            return AcquireResult.FAILED_FINAL
        if status == IdempotencyStatus.PROCESSING.value:
            if item["lease_expires_at"] > now:
                return AcquireResult.ALREADY_PROCESSING
            # Lease expirado — reassumir
            item["lease_expires_at"] = now + self._lease_duration
            return AcquireResult.ACQUIRED

        return AcquireResult.ALREADY_PROCESSING

    def mark_completed(self, message_id: str) -> None:
        key = f"MESSAGE#{message_id}"
        if key in self._items:
            self._items[key]["status"] = IdempotencyStatus.COMPLETED.value

    def mark_failed_final(self, message_id: str) -> None:
        key = f"MESSAGE#{message_id}"
        if key in self._items:
            self._items[key]["status"] = IdempotencyStatus.FAILED_FINAL.value

    def get_status(self, message_id: str) -> str | None:
        key = f"MESSAGE#{message_id}"
        item = self._items.get(key)
        return item["status"] if item else None


class FakeParticipantService:
    """Participant Service fake — registra chamadas e permite configurar respostas."""

    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self.disconnects: list[str] = []
        self._send_responses: list[SendMessageResult] = []
        self._renew_response: RenewConnectionResult | None = None

    def configure_send(self, *responses: SendMessageResult) -> None:
        """Configura respostas sequenciais para send_message."""
        self._send_responses = list(responses)

    def configure_renew(self, response: RenewConnectionResult) -> None:
        self._renew_response = response

    def send_message(
        self,
        connection_token: str,
        content: str,
        contact_id: str,
        source_message_id: str,
        content_type: str = "text/plain",
    ) -> SendMessageResult:
        self.sent_messages.append({
            "connection_token": connection_token,
            "content": content,
            "contact_id": contact_id,
            "source_message_id": source_message_id,
        })
        if self._send_responses:
            return self._send_responses.pop(0)
        return SendMessageResult(success=True, messages_sent=[SentMessageInfo("resp-id", "T")])

    def renew_connection(self, participant_token: str) -> RenewConnectionResult:
        if self._renew_response:
            return self._renew_response
        return RenewConnectionResult(success=True, connection_token="new-ct", expiry="2099-01-01T00:00:00Z")

    def disconnect_participant(self, connection_token: str):
        self.disconnects.append(connection_token)


def make_test_session(contact_id: str = "contact-001") -> SessionData:
    """Cria uma sessão de teste com tokens fake."""
    crypto = FakeCryptoService()
    return SessionData(
        contact_id=contact_id,
        participant_id="part-001",
        participant_token_encrypted=crypto.encrypt("pt-secret"),
        connection_token_encrypted=crypto.encrypt("ct-secret"),
        connection_token_expiry="2099-01-01T00:00:00Z",
        streaming_id="stream-001",
        status=SessionStatus.ACTIVE,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        expires_at=int(time.time()) + 86400,
        last_message_id="",
        handoff_requested=False,
    )
