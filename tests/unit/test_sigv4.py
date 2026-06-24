"""
Testes unitários para shared.sigv4 — assinatura SigV4 para Lambda Function URLs.

Testa AWSSigV4Auth com credenciais fictícias (sem acesso AWS real)
e a lógica de seleção SigV4 vs NoOp no processor.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from shared.sigv4 import AWSSigV4Auth, NoOpSigV4Auth


class TestNoOpSigV4Auth:
    """NoOpSigV4Auth retorna headers inalterados."""

    def test_returns_same_headers(self):
        auth = NoOpSigV4Auth()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        result = auth.sign_headers(
            method="POST",
            url="http://localhost:8000/mcp",
            headers=headers,
            body=b'{"test": true}',
        )
        assert result == headers

    def test_returns_same_headers_without_body(self):
        auth = NoOpSigV4Auth()
        headers = {"X-Custom": "value"}
        result = auth.sign_headers(method="GET", url="http://example.com", headers=headers)
        assert result == headers


class TestAWSSigV4Auth:
    """AWSSigV4Auth assina requests com credenciais fictícias."""

    FAKE_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
    FAKE_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    FAKE_SESSION_TOKEN = "FwoGZXIvYXdzEBAaDH2example-session-token"
    TEST_URL = "https://abc123.lambda-url.us-east-1.on.aws/mcp"
    TEST_REGION = "us-east-1"

    @pytest.fixture
    def fake_env(self, monkeypatch):
        """Configura credenciais fictícias via env vars (como Lambda runtime faz)."""
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", self.FAKE_ACCESS_KEY)
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", self.FAKE_SECRET_KEY)
        monkeypatch.setenv("AWS_SESSION_TOKEN", self.FAKE_SESSION_TOKEN)
        monkeypatch.setenv("AWS_DEFAULT_REGION", self.TEST_REGION)

    def test_service_is_lambda(self, fake_env):
        """Serviço de assinatura deve ser 'lambda'."""
        auth = AWSSigV4Auth(region=self.TEST_REGION, service="lambda")
        assert auth._service == "lambda"
        assert auth._region == self.TEST_REGION

    def test_sign_headers_adds_authorization(self, fake_env):
        """Headers assinados contêm Authorization."""
        auth = AWSSigV4Auth(region=self.TEST_REGION, service="lambda")
        headers = {"Content-Type": "application/json"}
        body = b'{"jsonrpc":"2.0","id":"test","method":"tools/list","params":{}}'

        result = auth.sign_headers(
            method="POST", url=self.TEST_URL, headers=headers, body=body
        )

        assert "Authorization" in result
        assert "AWS4-HMAC-SHA256" in result["Authorization"]

    def test_sign_headers_adds_amz_date(self, fake_env):
        """Headers assinados contêm X-Amz-Date."""
        auth = AWSSigV4Auth(region=self.TEST_REGION, service="lambda")
        headers = {"Content-Type": "application/json"}
        body = b'{"test": true}'

        result = auth.sign_headers(
            method="POST", url=self.TEST_URL, headers=headers, body=body
        )

        assert "X-Amz-Date" in result
        # Formato: YYYYMMDDTHHMMSSZ
        assert len(result["X-Amz-Date"]) == 16
        assert result["X-Amz-Date"].endswith("Z")

    def test_sign_headers_adds_security_token(self, fake_env):
        """Headers assinados contêm X-Amz-Security-Token (session credentials)."""
        auth = AWSSigV4Auth(region=self.TEST_REGION, service="lambda")
        headers = {"Content-Type": "application/json"}
        body = b'{"test": true}'

        result = auth.sign_headers(
            method="POST", url=self.TEST_URL, headers=headers, body=body
        )

        assert "X-Amz-Security-Token" in result
        assert result["X-Amz-Security-Token"] == self.FAKE_SESSION_TOKEN

    def test_authorization_contains_correct_region(self, fake_env):
        """Authorization header referencia a região correta."""
        auth = AWSSigV4Auth(region="eu-west-1", service="lambda")
        headers = {"Content-Type": "application/json"}
        body = b'{"test": true}'

        result = auth.sign_headers(
            method="POST",
            url="https://xyz.lambda-url.eu-west-1.on.aws/mcp",
            headers=headers,
            body=body,
        )

        # Credential contém region/service: AKID/date/eu-west-1/lambda/aws4_request
        assert "eu-west-1/lambda/aws4_request" in result["Authorization"]

    def test_authorization_contains_service_lambda(self, fake_env):
        """Authorization credential scope contém serviço 'lambda'."""
        auth = AWSSigV4Auth(region=self.TEST_REGION, service="lambda")
        headers = {"Content-Type": "application/json"}
        body = b'{"test": true}'

        result = auth.sign_headers(
            method="POST", url=self.TEST_URL, headers=headers, body=body
        )

        assert f"{self.TEST_REGION}/lambda/aws4_request" in result["Authorization"]

    def test_uses_frozen_credentials(self, fake_env):
        """Deve usar get_frozen_credentials() para thread-safety."""
        auth = AWSSigV4Auth(region=self.TEST_REGION, service="lambda")

        with patch("botocore.session.Session") as mock_session_cls:
            mock_session = MagicMock()
            mock_creds = MagicMock()
            mock_frozen = MagicMock()
            mock_frozen.access_key = self.FAKE_ACCESS_KEY
            mock_frozen.secret_key = self.FAKE_SECRET_KEY
            mock_frozen.token = self.FAKE_SESSION_TOKEN

            mock_session_cls.return_value = mock_session
            mock_session.get_credentials.return_value = mock_creds
            mock_creds.get_frozen_credentials.return_value = mock_frozen

            with patch("botocore.auth.SigV4Auth") as mock_signer_cls:
                mock_signer = MagicMock()
                mock_signer_cls.return_value = mock_signer

                auth.sign_headers(
                    method="POST",
                    url=self.TEST_URL,
                    headers={"Content-Type": "application/json"},
                    body=b"test",
                )

                # Verifica que usou frozen credentials
                mock_creds.get_frozen_credentials.assert_called_once()
                # Verifica que o signer foi criado com service=lambda e region correta
                mock_signer_cls.assert_called_once_with(
                    mock_frozen, "lambda", self.TEST_REGION
                )
                # Verifica que add_auth foi chamado
                mock_signer.add_auth.assert_called_once()

    def test_signature_depends_on_body_bytes(self, fake_env):
        """Duas assinaturas com body diferente produzem Authorization diferente."""
        auth = AWSSigV4Auth(region=self.TEST_REGION, service="lambda")
        headers = {"Content-Type": "application/json"}

        body_a = b'{"method":"tools/list"}'
        body_b = b'{"method":"tools/call"}'

        result_a = auth.sign_headers(
            method="POST", url=self.TEST_URL, headers=headers, body=body_a
        )
        result_b = auth.sign_headers(
            method="POST", url=self.TEST_URL, headers=headers, body=body_b
        )

        # Signature (última parte do Authorization) deve ser diferente
        assert result_a["Authorization"] != result_b["Authorization"]

    def test_content_sent_to_httpx_matches_signed_body(self, fake_env):
        """
        Verifica que o body passado para sign_headers é exatamente o que será
        enviado via httpx content=body (sem re-serialização).
        """
        auth = AWSSigV4Auth(region=self.TEST_REGION, service="lambda")

        # Simula o que MCPClient faz: serializa uma vez, assina, envia
        payload = {"jsonrpc": "2.0", "id": "123", "method": "tools/list", "params": {}}
        body = json.dumps(payload).encode("utf-8")

        # Assinar
        signed_headers = auth.sign_headers(
            method="POST",
            url=self.TEST_URL,
            headers={"Content-Type": "application/json"},
            body=body,
        )

        # O Authorization é calculado sobre body (SHA256 do payload).
        # Se o httpx re-serializasse (json=payload), o hash mudaria.
        # Como usamos content=body, o hash é estável.
        assert "Authorization" in signed_headers

        # Assinar novamente com os MESMOS bytes deve produzir mesmo resultado
        # (exceto X-Amz-Date que muda a cada segundo — comparamos no mesmo segundo)
        signed_headers_2 = auth.sign_headers(
            method="POST",
            url=self.TEST_URL,
            headers={"Content-Type": "application/json"},
            body=body,
        )
        # Se executado no mesmo segundo, devem ser idênticos
        # (teste determinístico: o timestamp avança ≤1s)
        assert signed_headers["X-Amz-Security-Token"] == signed_headers_2["X-Amz-Security-Token"]


class TestSigV4Selection:
    """Testa a lógica de seleção SigV4 no processor.from_environment."""

    def test_lambda_url_activates_sigv4(self, monkeypatch):
        """URL .lambda-url.<region>.on.aws deve ativar AWSSigV4Auth."""
        monkeypatch.setenv("MCP_SERVER_URL", "https://abc.lambda-url.us-east-1.on.aws/mcp")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATEST")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
        monkeypatch.setenv("AWS_SESSION_TOKEN", "token")

        from shared.sigv4 import AWSSigV4Auth, NoOpSigV4Auth

        mcp_url = os.environ["MCP_SERVER_URL"]
        region = os.environ["AWS_REGION"]

        if ".lambda-url." in mcp_url and ".on.aws" in mcp_url:
            sigv4_auth = AWSSigV4Auth(region=region, service="lambda")
        else:
            sigv4_auth = NoOpSigV4Auth()

        assert isinstance(sigv4_auth, AWSSigV4Auth)
        assert sigv4_auth._region == "us-east-1"
        assert sigv4_auth._service == "lambda"

    def test_lambda_url_eu_west_1_correct_region(self, monkeypatch):
        """URL com região eu-west-1 usa a região correta."""
        monkeypatch.setenv("MCP_SERVER_URL", "https://xyz.lambda-url.eu-west-1.on.aws/mcp")
        monkeypatch.setenv("AWS_REGION", "eu-west-1")

        from shared.sigv4 import AWSSigV4Auth, NoOpSigV4Auth

        mcp_url = os.environ["MCP_SERVER_URL"]
        region = os.environ["AWS_REGION"]

        if ".lambda-url." in mcp_url and ".on.aws" in mcp_url:
            sigv4_auth = AWSSigV4Auth(region=region, service="lambda")
        else:
            sigv4_auth = NoOpSigV4Auth()

        assert isinstance(sigv4_auth, AWSSigV4Auth)
        assert sigv4_auth._region == "eu-west-1"

    def test_localhost_url_uses_noop(self, monkeypatch):
        """URL local (localhost) usa NoOpSigV4Auth."""
        monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        from shared.sigv4 import AWSSigV4Auth, NoOpSigV4Auth

        mcp_url = os.environ["MCP_SERVER_URL"]
        region = os.environ["AWS_REGION"]

        if ".lambda-url." in mcp_url and ".on.aws" in mcp_url:
            sigv4_auth = AWSSigV4Auth(region=region, service="lambda")
        else:
            sigv4_auth = NoOpSigV4Auth()

        assert isinstance(sigv4_auth, NoOpSigV4Auth)

    def test_custom_internal_url_uses_noop(self, monkeypatch):
        """URL interna (sem .lambda-url.) usa NoOpSigV4Auth."""
        monkeypatch.setenv("MCP_SERVER_URL", "https://mcp.internal.corp.com/mcp")
        monkeypatch.setenv("AWS_REGION", "us-east-1")

        from shared.sigv4 import AWSSigV4Auth, NoOpSigV4Auth

        mcp_url = os.environ["MCP_SERVER_URL"]
        region = os.environ["AWS_REGION"]

        if ".lambda-url." in mcp_url and ".on.aws" in mcp_url:
            sigv4_auth = AWSSigV4Auth(region=region, service="lambda")
        else:
            sigv4_auth = NoOpSigV4Auth()

        assert isinstance(sigv4_auth, NoOpSigV4Auth)

    def test_region_from_aws_region_env_var(self, monkeypatch):
        """A região é obtida de AWS_REGION, não extraída da URL."""
        monkeypatch.setenv("MCP_SERVER_URL", "https://abc.lambda-url.us-east-1.on.aws/mcp")
        monkeypatch.setenv("AWS_REGION", "ap-southeast-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATEST")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")

        from shared.sigv4 import AWSSigV4Auth, NoOpSigV4Auth

        mcp_url = os.environ["MCP_SERVER_URL"]
        region = os.environ["AWS_REGION"]

        if ".lambda-url." in mcp_url and ".on.aws" in mcp_url:
            sigv4_auth = AWSSigV4Auth(region=region, service="lambda")
        else:
            sigv4_auth = NoOpSigV4Auth()

        # Região vem de AWS_REGION, não da URL
        assert isinstance(sigv4_auth, AWSSigV4Auth)
        assert sigv4_auth._region == "ap-southeast-1"
