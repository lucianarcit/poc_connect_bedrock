"""Testes da Lambda Initializer."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.stub import Stubber

from initializer.service import (
    InitializationContext,
    InitializerService,
    extract_context,
    generate_participant_client_token,
    generate_streaming_client_token,
)
from integrator.exceptions import SessionStatus


# --- Fixtures ---


def _valid_event(
    contact_id: str = "contact-001",
    instance_arn: str = "arn:aws:connect:us-east-1:123456789012:instance/inst-001",
    channel: str = "CHAT",
) -> dict:
    return {
        "Details": {
            "ContactData": {
                "ContactId": contact_id,
                "InitialContactId": contact_id,
                "InstanceARN": instance_arn,
                "Channel": channel,
                "Attributes": {},
            },
            "Parameters": {},
        },
        "Name": "ContactFlowEvent",
    }


@pytest.fixture
def connect_client():
    return boto3.client("connect", region_name="us-east-1")


@pytest.fixture
def participant_client():
    return boto3.client("connectparticipant", region_name="us-east-1")


@pytest.fixture
def kms_client():
    return boto3.client("kms", region_name="us-east-1")


@pytest.fixture
def dynamodb_client():
    return boto3.client("dynamodb", region_name="us-east-1")


@pytest.fixture
def service(connect_client, participant_client, kms_client, dynamodb_client):
    return InitializerService(
        connect_client=connect_client,
        participant_client=participant_client,
        kms_client=kms_client,
        dynamodb_client=dynamodb_client,
        sns_topic_arn="arn:aws:sns:us-east-1:123456789012:topic",
        kms_key_id="alias/test-key",
        table_name="test-sessions",
        lease_seconds=30,
    )


# --- extract_context ---


class TestExtractContext:
    def test_valid_event(self):
        ctx = extract_context(_valid_event())
        assert ctx.contact_id == "contact-001"
        assert ctx.instance_id == "inst-001"
        assert ctx.channel == "CHAT"

    def test_no_details(self):
        with pytest.raises(ValueError, match="Details"):
            extract_context({})

    def test_no_contact_data(self):
        with pytest.raises(ValueError, match="ContactData"):
            extract_context({"Details": {}})

    def test_no_contact_id(self):
        event = _valid_event()
        event["Details"]["ContactData"]["ContactId"] = ""
        with pytest.raises(ValueError, match="ContactId"):
            extract_context(event)

    def test_no_instance_arn(self):
        event = _valid_event()
        event["Details"]["ContactData"]["InstanceARN"] = ""
        with pytest.raises(ValueError, match="InstanceARN"):
            extract_context(event)

    def test_non_chat_channel(self):
        event = _valid_event(channel="VOICE")
        with pytest.raises(ValueError, match="CHAT"):
            extract_context(event)

    def test_instance_id_from_arn(self):
        arn = "arn:aws:connect:eu-west-1:999999999999:instance/my-inst-id"
        ctx = extract_context(_valid_event(instance_arn=arn))
        assert ctx.instance_id == "my-inst-id"


# --- ClientToken determinísticos ---


class TestClientTokens:
    def test_streaming_token_deterministic(self):
        t1 = generate_streaming_client_token("inst", "contact", "arn:sns")
        t2 = generate_streaming_client_token("inst", "contact", "arn:sns")
        assert t1 == t2

    def test_streaming_token_different_inputs(self):
        t1 = generate_streaming_client_token("inst1", "contact", "arn:sns")
        t2 = generate_streaming_client_token("inst2", "contact", "arn:sns")
        assert t1 != t2

    def test_participant_token_deterministic(self):
        t1 = generate_participant_client_token("inst", "contact")
        t2 = generate_participant_client_token("inst", "contact")
        assert t1 == t2

    def test_participant_token_different_contacts(self):
        t1 = generate_participant_client_token("inst", "c1")
        t2 = generate_participant_client_token("inst", "c2")
        assert t1 != t2

    def test_retry_reuses_same_tokens(self):
        """Retry do mesmo contato deve gerar os mesmos ClientTokens."""
        t1_s = generate_streaming_client_token("i", "c", "arn")
        t1_p = generate_participant_client_token("i", "c")
        # Simulando retry
        t2_s = generate_streaming_client_token("i", "c", "arn")
        t2_p = generate_participant_client_token("i", "c")
        assert t1_s == t2_s
        assert t1_p == t2_p


# --- Inicialização completa ---


class TestInitializeSuccess:
    def test_full_initialization(
        self, connect_client, participant_client, kms_client, dynamodb_client, service
    ):
        """Inicialização completa com sucesso."""
        with (
            Stubber(connect_client) as cs,
            Stubber(participant_client) as ps,
            Stubber(kms_client) as ks,
            Stubber(dynamodb_client) as ds,
        ):
            # get_item → NOT_FOUND
            ds.add_response("get_item", {})
            # put_item → reserva OK
            ds.add_response("put_item", {})
            # StartContactStreaming
            cs.add_response("start_contact_streaming", {"StreamingId": "stream-001"})
            # CreateParticipant
            cs.add_response("create_participant", {
                "ParticipantId": "part-001",
                "ParticipantCredentials": {"ParticipantToken": "pt-secret"},
            })
            # CreateParticipantConnection
            ps.add_response("create_participant_connection", {
                "ConnectionCredentials": {
                    "ConnectionToken": "ct-secret",
                    "Expiry": "2024-06-15T16:00:00Z",
                },
            })
            # KMS encrypt (2x)
            ks.add_response("encrypt", {"CiphertextBlob": b"enc-pt"})
            ks.add_response("encrypt", {"CiphertextBlob": b"enc-ct"})
            # update_item → ACTIVE
            ds.add_response("update_item", {})

            ctx = InitializationContext(
                contact_id="contact-001",
                instance_id="inst-001",
                initial_contact_id="contact-001",
                channel="CHAT",
            )
            result = service.initialize(ctx)

        assert result["status"] == "SUCCESS"
        assert result["botInitialized"] == "true"


class TestInitializeAlreadyActive:
    def test_session_active_complete_returns_success(
        self, connect_client, participant_client, kms_client, dynamodb_client, service
    ):
        """Sessão ACTIVE com dados completos retorna SUCCESS sem chamar APIs."""
        with Stubber(dynamodb_client) as ds:
            ds.add_response("get_item", {
                "Item": {
                    "pk": {"S": "CONTACT#contact-001"},
                    "status": {"S": "ACTIVE"},
                    "participant_id": {"S": "part-001"},
                    "connection_token_encrypted": {"B": b"enc-token"},
                    "connection_token_expiry": {"S": "2024-06-15T16:00:00Z"},
                }
            })

            ctx = InitializationContext("contact-001", "inst-001", "contact-001", "CHAT")
            result = service.initialize(ctx)

        assert result["status"] == "SUCCESS"


class TestInitializeLeaseActive:
    def test_initializing_lease_active_returns_error(
        self, connect_client, participant_client, kms_client, dynamodb_client, service
    ):
        """Sessão INITIALIZING com lease ativo não deve retornar SUCCESS falso."""
        future_lease = int(time.time()) + 999
        with Stubber(dynamodb_client) as ds:
            ds.add_response("get_item", {
                "Item": {
                    "pk": {"S": "CONTACT#contact-001"},
                    "status": {"S": "INITIALIZING"},
                    "initialization_lease_expires_at": {"N": str(future_lease)},
                }
            })

            ctx = InitializationContext("contact-001", "inst-001", "contact-001", "CHAT")
            result = service.initialize(ctx)

        assert result["status"] == "ERROR"
        assert result["errorCode"] == "INITIALIZATION_IN_PROGRESS"


class TestInitializeLeaseExpired:
    def test_initializing_lease_expired_allows_retry(
        self, connect_client, participant_client, kms_client, dynamodb_client, service
    ):
        """Sessão INITIALIZING com lease expirado permite reassumir."""
        expired_lease = int(time.time()) - 10
        with (
            Stubber(connect_client) as cs,
            Stubber(participant_client) as ps,
            Stubber(kms_client) as ks,
            Stubber(dynamodb_client) as ds,
        ):
            # get_item → INITIALIZING, lease expirado
            ds.add_response("get_item", {
                "Item": {
                    "pk": {"S": "CONTACT#contact-001"},
                    "status": {"S": "INITIALIZING"},
                    "initialization_lease_expires_at": {"N": str(expired_lease)},
                }
            })
            # put_item → ConditionalCheckFailed (item existe)
            ds.add_client_error("put_item", service_error_code="ConditionalCheckFailedException")
            # update_item → reassumir lease OK
            ds.add_response("update_item", {})
            # APIs Connect
            cs.add_response("start_contact_streaming", {"StreamingId": "s-002"})
            cs.add_response("create_participant", {
                "ParticipantId": "p-002",
                "ParticipantCredentials": {"ParticipantToken": "pt-2"},
            })
            ps.add_response("create_participant_connection", {
                "ConnectionCredentials": {"ConnectionToken": "ct-2", "Expiry": "2024-06-15T17:00:00Z"},
            })
            ks.add_response("encrypt", {"CiphertextBlob": b"enc1"})
            ks.add_response("encrypt", {"CiphertextBlob": b"enc2"})
            ds.add_response("update_item", {})

            ctx = InitializationContext("contact-001", "inst-001", "contact-001", "CHAT")
            result = service.initialize(ctx)

        assert result["status"] == "SUCCESS"


class TestInitializeErrors:
    def test_start_streaming_fails(
        self, connect_client, participant_client, kms_client, dynamodb_client, service
    ):
        """Falha no StartContactStreaming retorna ERROR."""
        with (
            Stubber(connect_client) as cs,
            Stubber(dynamodb_client) as ds,
        ):
            ds.add_response("get_item", {})
            ds.add_response("put_item", {})
            cs.add_client_error("start_contact_streaming", service_error_code="InternalServerError")

            ctx = InitializationContext("contact-001", "inst-001", "contact-001", "CHAT")
            result = service.initialize(ctx)

        assert result["status"] == "ERROR"

    def test_create_participant_fails(
        self, connect_client, participant_client, kms_client, dynamodb_client, service
    ):
        """Falha no CreateParticipant retorna ERROR."""
        with (
            Stubber(connect_client) as cs,
            Stubber(dynamodb_client) as ds,
        ):
            ds.add_response("get_item", {})
            ds.add_response("put_item", {})
            cs.add_response("start_contact_streaming", {"StreamingId": "s"})
            cs.add_client_error("create_participant", service_error_code="ThrottlingException")

            ctx = InitializationContext("contact-001", "inst-001", "contact-001", "CHAT")
            result = service.initialize(ctx)

        assert result["status"] == "ERROR"

    def test_kms_encrypt_fails(
        self, connect_client, participant_client, kms_client, dynamodb_client, service
    ):
        """Falha no KMS encrypt retorna ERROR."""
        with (
            Stubber(connect_client) as cs,
            Stubber(participant_client) as ps,
            Stubber(kms_client) as ks,
            Stubber(dynamodb_client) as ds,
        ):
            ds.add_response("get_item", {})
            ds.add_response("put_item", {})
            cs.add_response("start_contact_streaming", {"StreamingId": "s"})
            cs.add_response("create_participant", {
                "ParticipantId": "p", "ParticipantCredentials": {"ParticipantToken": "t"},
            })
            ps.add_response("create_participant_connection", {
                "ConnectionCredentials": {"ConnectionToken": "c", "Expiry": "e"},
            })
            ks.add_client_error("encrypt", service_error_code="KMSInternalException")

            ctx = InitializationContext("contact-001", "inst-001", "contact-001", "CHAT")
            result = service.initialize(ctx)

        assert result["status"] == "ERROR"


class TestInitializeResponseSafety:
    def test_response_never_contains_tokens(
        self, connect_client, participant_client, kms_client, dynamodb_client, service
    ):
        """A resposta ao Contact Flow nunca deve conter tokens."""
        with (
            Stubber(connect_client) as cs,
            Stubber(participant_client) as ps,
            Stubber(kms_client) as ks,
            Stubber(dynamodb_client) as ds,
        ):
            ds.add_response("get_item", {})
            ds.add_response("put_item", {})
            cs.add_response("start_contact_streaming", {"StreamingId": "s"})
            cs.add_response("create_participant", {
                "ParticipantId": "p",
                "ParticipantCredentials": {"ParticipantToken": "SECRET-PT-123"},
            })
            ps.add_response("create_participant_connection", {
                "ConnectionCredentials": {"ConnectionToken": "SECRET-CT-456", "Expiry": "e"},
            })
            ks.add_response("encrypt", {"CiphertextBlob": b"enc1"})
            ks.add_response("encrypt", {"CiphertextBlob": b"enc2"})
            ds.add_response("update_item", {})

            ctx = InitializationContext("contact-001", "inst-001", "contact-001", "CHAT")
            result = service.initialize(ctx)

        # Serializar e verificar ausência de tokens
        result_str = str(result)
        assert "SECRET-PT-123" not in result_str
        assert "SECRET-CT-456" not in result_str
        assert "enc1" not in result_str


class TestInitializeTimeout:
    def test_within_8_seconds(
        self, connect_client, participant_client, kms_client, dynamodb_client, service
    ):
        """Com mocks, a execução deve completar instantaneamente (<8s)."""
        with (
            Stubber(connect_client) as cs,
            Stubber(participant_client) as ps,
            Stubber(kms_client) as ks,
            Stubber(dynamodb_client) as ds,
        ):
            ds.add_response("get_item", {})
            ds.add_response("put_item", {})
            cs.add_response("start_contact_streaming", {"StreamingId": "s"})
            cs.add_response("create_participant", {
                "ParticipantId": "p", "ParticipantCredentials": {"ParticipantToken": "t"},
            })
            ps.add_response("create_participant_connection", {
                "ConnectionCredentials": {"ConnectionToken": "c", "Expiry": "e"},
            })
            ks.add_response("encrypt", {"CiphertextBlob": b"e1"})
            ks.add_response("encrypt", {"CiphertextBlob": b"e2"})
            ds.add_response("update_item", {})

            start = time.time()
            ctx = InitializationContext("contact-001", "inst-001", "contact-001", "CHAT")
            result = service.initialize(ctx)
            elapsed = time.time() - start

        assert result["status"] == "SUCCESS"
        assert elapsed < 8.0  # Must complete well within 8s
