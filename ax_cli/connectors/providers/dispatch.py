"""Resolve a registry connector row and execute a provider tool."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from ax_cli.connectors.activity import (
    record_connector_tool_finished,
    record_connector_tool_started,
)
from ax_cli.connectors.filtering import (
    assert_tool_allowed,
    resolve_tool_filter_policy,
)
from ax_cli.connectors.registry import find_connector, load_connectors_registry

from .base import ConnectorProviderError, ToolCallResult, ToolSearchResult
from .catalog import PROVIDER_COMPOSIO, PROVIDER_HTTP_MCP
from .composio_catalog import (
    list_composio_tools,
    search_composio_tools_catalog,
    search_composio_tools_intent,
)
from .http_mcp_catalog import list_http_mcp_tools, search_http_mcp_tools_catalog
from .registry import get_provider_adapter

SearchMode = Literal["catalog", "intent", "auto"]


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


def _require_connector_row(
    registry: dict[str, Any] | None,
    connector_ref: str,
) -> dict[str, Any]:
    reg = registry if registry is not None else load_connectors_registry()
    row = find_connector(reg, connector_ref)
    if not row:
        raise ConnectorProviderError(f"unknown connector: {connector_ref!r}")
    if not bool(row.get("enabled", True)):
        raise ConnectorProviderError(f"connector {row.get('name')!r} is disabled")
    return row


def _provider_id(row: dict[str, Any]) -> str:
    return str(row.get("provider") or "").strip().lower()


def list_connector_tools(
    connector_ref: str,
    *,
    registry: dict[str, Any] | None = None,
    query: str | None = None,
    toolkit_slug: str | None = None,
    tool_slugs: list[str] | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List tools for a connector (provider catalog + Gateway policy)."""
    row = _require_connector_row(registry, connector_ref)
    provider = _provider_id(row)
    policy = resolve_tool_filter_policy(row)
    adapter = adapter_for_connector(row)
    if provider == PROVIDER_COMPOSIO:
        page = list_composio_tools(
            adapter,
            policy,
            query=query,
            toolkit_slug=toolkit_slug,
            tool_slugs=tool_slugs,
            limit=limit,
            cursor=cursor,
        )
    elif provider == PROVIDER_HTTP_MCP:
        if toolkit_slug or tool_slugs or cursor:
            pass  # ignored for MCP tools/list
        page = list_http_mcp_tools(adapter, policy, query=query, limit=limit)
    else:
        raise ConnectorProviderError(
            f"tool listing is not implemented for provider {provider!r} "
            f"(supported: {PROVIDER_COMPOSIO}, {PROVIDER_HTTP_MCP})"
        )
    page["connector_name"] = row.get("name")
    page["provider"] = provider
    return page


def search_connector_tools(
    connector_ref: str,
    use_case: str,
    *,
    registry: dict[str, Any] | None = None,
    mode: SearchMode = "auto",
    known_fields: str | None = None,
    session_id: str | None = None,
    limit: int | None = None,
) -> ToolSearchResult:
    """Search tools by natural-language use case (intent or catalog query)."""
    row = _require_connector_row(registry, connector_ref)
    provider = _provider_id(row)
    policy = resolve_tool_filter_policy(row)
    adapter = adapter_for_connector(row)

    if provider == PROVIDER_HTTP_MCP:
        return search_http_mcp_tools_catalog(adapter, policy, use_case, limit=limit)

    if provider != PROVIDER_COMPOSIO:
        raise ConnectorProviderError(
            f"tool search is not implemented for provider {provider!r} "
            f"(supported: {PROVIDER_COMPOSIO}, {PROVIDER_HTTP_MCP})"
        )

    cfg = row.get("config") if isinstance(row.get("config"), dict) else {}
    configured_mode = str(cfg.get("search_mode") or "auto").strip().lower()
    effective_mode = mode if mode != "auto" else configured_mode  # type: ignore[assignment]
    if effective_mode not in {"catalog", "intent", "auto"}:
        effective_mode = "auto"

    if effective_mode == "catalog":
        result = search_composio_tools_catalog(adapter, policy, use_case, limit=limit)
    elif effective_mode == "intent":
        result = search_composio_tools_intent(
            adapter,
            policy,
            use_case,
            known_fields=known_fields,
            session_id=session_id,
        )
    else:
        result = search_composio_tools_intent(
            adapter,
            policy,
            use_case,
            known_fields=known_fields,
            session_id=session_id,
        )
        if not result.successful or not result.tools:
            result = search_composio_tools_catalog(adapter, policy, use_case, limit=limit)
    return result


def execute_connector_tool(
    connector_ref: str,
    tool_slug: str,
    arguments: dict[str, Any] | None = None,
    *,
    registry: dict[str, Any] | None = None,
    version: str | None = None,
    connected_account_id: str | None = None,
    record_activity: bool = True,
    skip_policy_check: bool = False,
) -> ToolCallResult:
    """Load connector by name/id and execute ``tool_slug`` via its provider adapter."""
    reg = registry if registry is not None else load_connectors_registry()
    row = find_connector(reg, connector_ref)
    if not row:
        raise ConnectorProviderError(f"unknown connector: {connector_ref!r}")

    policy = resolve_tool_filter_policy(row)
    if not skip_policy_check:
        assert_tool_allowed(tool_slug, policy, connector_name=str(row.get("name") or ""))

    tool_call_id = str(uuid.uuid4())
    if record_activity:
        started = record_connector_tool_started(row, tool_slug, tool_call_id=tool_call_id)
        tool_call_id = str(started.get("tool_call_id") or tool_call_id)

    cfg = row.get("config") if isinstance(row.get("config"), dict) else {}
    version_eff = version or (str(cfg.get("tool_version") or cfg.get("version") or "").strip() or None)
    connected_eff = connected_account_id or (
        str(cfg.get("connected_account_id") or "").strip() or None
    )

    try:
        adapter = adapter_for_connector(row)
        result = adapter.execute_tool(
            tool_slug,
            arguments,
            version=version_eff,
            connected_account_id=connected_eff,
        )
    except ConnectorProviderError as exc:
        if record_activity:
            record_connector_tool_finished(
                row,
                tool_slug,
                tool_call_id=tool_call_id,
                successful=False,
                error=str(exc),
            )
        raise

    if record_activity:
        record_connector_tool_finished(
            row,
            tool_slug,
            tool_call_id=tool_call_id,
            successful=result.successful,
            error=result.error,
            log_id=result.log_id,
        )
    return result
