"""
Assinatura SigV4 para requests httpx destinados a Lambda Function URLs.

Usa botocore.auth.SigV4Auth para assinar requests HTTP com as credenciais
temporárias da execution role da Lambda (disponíveis via environment variables
ou instance metadata).

Uso:
    from shared.sigv4 import SigV4Auth

    auth = SigV4Auth(region="us-east-1")
    headers = auth.sign_headers(
        method="POST",
        url="https://xxx.lambda-url.us-east-1.on.aws/mcp",
        headers={"Content-Type": "application/json"},
        body=b'{"jsonrpc":"2.0",...}',
    )
    # headers agora contém Authorization, X-Amz-Date, X-Amz-Security-Token
"""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlparse


class SigV4Signer(Protocol):
    """Interface para assinatura SigV4 (injetável para testes)."""

    def sign_headers(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> dict[str, str]:
        """Retorna headers assinados (incluindo Authorization)."""
        ...


class AWSSigV4Auth:
    """
    Implementação real de SigV4 usando botocore.

    Obtém credenciais automaticamente da execution role da Lambda
    via botocore.session (env vars AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN — preenchidos automaticamente pelo Lambda runtime).
    """

    def __init__(self, region: str, service: str = "lambda") -> None:
        self._region = region
        self._service = service

    def sign_headers(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> dict[str, str]:
        """Assina o request e retorna headers com Authorization + X-Amz-*."""
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
        from botocore.session import Session

        session = Session()
        credentials = session.get_credentials().get_frozen_credentials()

        # Construir AWSRequest
        aws_request = AWSRequest(
            method=method,
            url=url,
            headers=headers,
            data=body or b"",
        )

        # Assinar
        signer = SigV4Auth(credentials, self._service, self._region)
        signer.add_auth(aws_request)

        # Retornar headers assinados (inclui Authorization, X-Amz-Date, X-Amz-Security-Token)
        return dict(aws_request.headers)


class NoOpSigV4Auth:
    """
    Implementação no-op para desenvolvimento local e testes.
    Não assina nada — retorna headers inalterados.
    """

    def sign_headers(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None = None,
    ) -> dict[str, str]:
        return headers
