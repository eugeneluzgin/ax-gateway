"""Provider catalog: supported outbound connector types and capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROVIDER_COMPOSIO = "composio"
PROVIDER_HTTP_MCP = "http_mcp"

CAP_EXECUTE = "execute"
CAP_LIST_TOOLS = "list_tools"
CAP_INTENT_SEARCH = "intent_search"


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    """One registered connector provider type."""

    id: str
    label: str
    description: str
    capabilities: frozenset[str]
    auth_env_keys: tuple[str, ...]
    config_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "capabilities": sorted(self.capabilities),
            "auth_env_keys": list(self.auth_env_keys),
            "config_fields": list(self.config_fields),
            "supports_execute": CAP_EXECUTE in self.capabilities,
            "supports_list_tools": CAP_LIST_TOOLS in self.capabilities,
            "supports_intent_search": CAP_INTENT_SEARCH in self.capabilities,
        }


_PROVIDER_CATALOG: dict[str, ProviderDefinition] = {
    PROVIDER_COMPOSIO: ProviderDefinition(
        id=PROVIDER_COMPOSIO,
        label="Composio",
        description="Composio tool API (execute, catalog list, and COMPOSIO_SEARCH_TOOLS intent search).",
        capabilities=frozenset({CAP_EXECUTE, CAP_LIST_TOOLS, CAP_INTENT_SEARCH}),
        auth_env_keys=("COMPOSIO_API_KEY", "COMPOSIO_KEY", "COMPOSIO_APIKEY", "COMPOSIO_USER_ID"),
        config_fields=(
            "user_id",
            "base_url",
            "tool_version",
            "connected_account_id",
            "allowed_tools",
            "denied_tools",
            "toolkits",
            "tools_limit",
            "search_mode",
            "agent_name",
        ),
    ),
    PROVIDER_HTTP_MCP: ProviderDefinition(
        id=PROVIDER_HTTP_MCP,
        label="HTTP MCP",
        description=(
            "Generic MCP server over HTTP JSON-RPC (tools/list and tools/call). "
            "Use for self-hosted MCP, Composio hosted MCP URLs, or other streamable HTTP endpoints."
        ),
        capabilities=frozenset({CAP_EXECUTE, CAP_LIST_TOOLS}),
        auth_env_keys=("MCP_BEARER_TOKEN", "MCP_AUTHORIZATION", "MCP_API_KEY"),
        config_fields=("base_url", "protocol_version", "api_key_header", "skip_initialize"),
    ),
}

SUPPORTED_PROVIDERS: frozenset[str] = frozenset(_PROVIDER_CATALOG.keys())


def provider_definition(provider_id: str) -> ProviderDefinition:
    pid = str(provider_id or "").strip().lower()
    definition = _PROVIDER_CATALOG.get(pid)
    if definition is None:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise ValueError(f"unsupported provider {provider_id!r} (supported: {supported})")
    return definition


def is_supported_provider(provider_id: str) -> bool:
    return str(provider_id or "").strip().lower() in _PROVIDER_CATALOG


def list_provider_definitions() -> list[ProviderDefinition]:
    return [_PROVIDER_CATALOG[pid] for pid in sorted(_PROVIDER_CATALOG)]


def providers_payload() -> dict[str, Any]:
    items = [definition.to_dict() for definition in list_provider_definitions()]
    return {"providers": items, "count": len(items)}
