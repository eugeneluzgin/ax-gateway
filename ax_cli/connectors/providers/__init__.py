"""Outbound connector provider adapters (Composio, future vendors)."""

from .base import ConnectorProviderError, ToolCallResult, ToolCatalogEntry, ToolSearchResult
from .dispatch import (
    adapter_for_connector,
    execute_connector_tool,
    list_connector_tools,
    search_connector_tools,
)
from .registry import SUPPORTED_PROVIDERS, get_provider_adapter

__all__ = [
    "ConnectorProviderError",
    "SUPPORTED_PROVIDERS",
    "ToolCallResult",
    "ToolCatalogEntry",
    "ToolSearchResult",
    "adapter_for_connector",
    "execute_connector_tool",
    "get_provider_adapter",
    "list_connector_tools",
    "search_connector_tools",
]
