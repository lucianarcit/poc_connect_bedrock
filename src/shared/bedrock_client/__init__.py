"""Cliente Amazon Bedrock Converse API para a POC Connect + Bedrock."""

from shared.bedrock_client.client import BedrockClient
from shared.bedrock_client.exceptions import (
    BedrockConfigurationError,
    BedrockError,
    BedrockFatalError,
    BedrockTimeoutError,
    BedrockTransientError,
)

__all__ = [
    "BedrockClient",
    "BedrockConfigurationError",
    "BedrockError",
    "BedrockFatalError",
    "BedrockTimeoutError",
    "BedrockTransientError",
]
