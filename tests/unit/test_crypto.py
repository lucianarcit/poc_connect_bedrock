"""Testes do CryptoService (KMS e Fake)."""

from __future__ import annotations

import boto3
import pytest
from botocore.stub import Stubber

from shared.crypto import FakeCryptoService, KMSCryptoService


class TestFakeCryptoService:
    def test_encrypt_decrypt_roundtrip(self):
        crypto = FakeCryptoService()
        encrypted = crypto.encrypt("my-secret-token")
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == "my-secret-token"

    def test_invalid_ciphertext(self):
        crypto = FakeCryptoService()
        with pytest.raises(ValueError):
            crypto.decrypt(b"invalid-data")


class TestKMSCryptoService:
    @pytest.fixture
    def kms_client(self):
        return boto3.client("kms", region_name="us-east-1")

    def test_encrypt(self, kms_client):
        """Encrypt deve chamar KMS e retornar CiphertextBlob."""
        crypto = KMSCryptoService(kms_client, "alias/test-key")
        with Stubber(kms_client) as stubber:
            stubber.add_response("encrypt", {"CiphertextBlob": b"encrypted-blob"})
            result = crypto.encrypt("plain-token")

        assert result == b"encrypted-blob"

    def test_decrypt(self, kms_client):
        """Decrypt deve chamar KMS e retornar Plaintext decodificado."""
        crypto = KMSCryptoService(kms_client, "alias/test-key")
        with Stubber(kms_client) as stubber:
            stubber.add_response("decrypt", {"Plaintext": b"decrypted-token"})
            result = crypto.decrypt(b"some-ciphertext")

        assert result == "decrypted-token"

    def test_encrypt_error(self, kms_client):
        """Erro no KMS deve propagar."""
        crypto = KMSCryptoService(kms_client, "alias/test-key")
        with Stubber(kms_client) as stubber:
            stubber.add_client_error("encrypt", service_error_code="KMSInternalException")
            with pytest.raises(Exception):
                crypto.encrypt("token")

    def test_decrypt_error(self, kms_client):
        """Erro no KMS deve propagar."""
        crypto = KMSCryptoService(kms_client, "alias/test-key")
        with Stubber(kms_client) as stubber:
            stubber.add_client_error("decrypt", service_error_code="InvalidCiphertextException")
            with pytest.raises(Exception):
                crypto.decrypt(b"bad")
