"""Outbound connector provider adapters (Composio, future vendors)."""

from .base import ConnectorProviderError, ToolCallResult, ToolCatalogEntry, ToolSearchResult
from .catalog import ProviderDefinition, list_provider_definitions, providers_payload
from .dispatch import (
    adapter_for_connector,
    execute_connector_tool,
    list_connector_tools,
    search_connector_tools,
)
from .registry import SUPPORTED_PROVIDERS, get_provider_adapter

__all__ = [
    "ConnectorProviderError",
    "ProviderDefinition",
    "SUPPORTED_PROVIDERS",
    "list_provider_definitions",
    "providers_payload",
    "ToolCallResult",
    "ToolCatalogEntry",
    "ToolSearchResult",
    "adapter_for_connector",
    "execute_connector_tool",
    "get_provider_adapter",
    "list_connector_tools",
    "search_connector_tools",
]
