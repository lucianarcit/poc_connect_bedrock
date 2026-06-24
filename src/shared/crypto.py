"""
Abstração de criptografia KMS injetável e testável.

Nunca loga tokens ou plaintexts.
"""

from __future__ import annotations

from typing import Any, Protocol


class CryptoService(Protocol):
    """Interface para criptografia/descriptografia."""

    def encrypt(self, plaintext: str) -> bytes:
        """Criptografa texto. Retorna blob opaco."""
        ...

    def decrypt(self, ciphertext: bytes) -> str:
        """Descriptografa blob. Retorna texto."""
        ...


class KMSCryptoService:
    """Implementação real com AWS KMS."""

    def __init__(self, kms_client: Any, key_id: str) -> None:
        self._client = kms_client
        self._key_id = key_id

    def encrypt(self, plaintext: str) -> bytes:
        response = self._client.encrypt(
            KeyId=self._key_id,
            Plaintext=plaintext.encode("utf-8"),
        )
        return response["CiphertextBlob"]

    def decrypt(self, ciphertext: bytes) -> str:
        response = self._client.decrypt(CiphertextBlob=ciphertext)
        return response["Plaintext"].decode("utf-8")


class FakeCryptoService:
    """Implementação fake para testes (sem KMS real)."""

    def encrypt(self, plaintext: str) -> bytes:
        return b"ENC:" + plaintext.encode("utf-8")

    def decrypt(self, ciphertext: bytes) -> str:
        prefix = b"ENC:"
        if ciphertext.startswith(prefix):
            return ciphertext[len(prefix):].decode("utf-8")
        raise ValueError("Invalid ciphertext for FakeCryptoService")
