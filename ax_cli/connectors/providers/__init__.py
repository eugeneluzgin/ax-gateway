"""Outbound connector provider adapters (Composio, future vendors)."""

from .base import ConnectorProviderError, ToolCallResult
from .dispatch import adapter_for_connector, execute_connector_tool
from .registry import SUPPORTED_PROVIDERS, get_provider_adapter

__all__ = [
    "ConnectorProviderError",
    "SUPPORTED_PROVIDERS",
    "ToolCallResult",
    "adapter_for_connector",
    "execute_connector_tool",
    "get_provider_adapter",
]
