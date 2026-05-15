"""Resolve a registry connector row and execute a provider tool."""

from __future__ import annotations

from typing import Any

from ax_cli.connectors.registry import find_connector, load_connectors_registry

from .base import ConnectorProviderError, ToolCallResult
from .registry import get_provider_adapter


def adapter_for_connector(connector: dict[str, Any]) -> Any:
    """Build a provider adapter from a connector registry row."""
    if not isinstance(connector, dict):
        raise ConnectorProviderError("connector row must be an object")
    if not bool(connector.get("enabled", True)):
        raise ConnectorProviderError(f"connector {connector.get('name')!r} is disabled")
    provider = str(connector.get("provider") or "").strip().lower()
    if not provider:
        raise ConnectorProviderError("connector provider is missing")
    return get_provider_adapter(provider, connector)


def execute_connector_tool(
    connector_ref: str,
    tool_slug: str,
    arguments: dict[str, Any] | None = None,
    *,
    registry: dict[str, Any] | None = None,
    version: str | None = None,
    connected_account_id: str | None = None,
) -> ToolCallResult:
    """Load connector by name/id and execute ``tool_slug`` via its provider adapter."""
    reg = registry if registry is not None else load_connectors_registry()
    row = find_connector(reg, connector_ref)
    if not row:
        raise ConnectorProviderError(f"unknown connector: {connector_ref!r}")
    adapter = adapter_for_connector(row)
    cfg = row.get("config") if isinstance(row.get("config"), dict) else {}
    version_eff = version or (str(cfg.get("tool_version") or cfg.get("version") or "").strip() or None)
    connected_eff = connected_account_id or (
        str(cfg.get("connected_account_id") or "").strip() or None
    )
    return adapter.execute_tool(
        tool_slug,
        arguments,
        version=version_eff,
        connected_account_id=connected_eff,
    )
