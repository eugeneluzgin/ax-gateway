"""Shared types for connector provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..errors import ConnectorProviderError

__all__ = ["ConnectorProviderError", "ProviderAdapter", "ToolCallResult", "ToolCatalogEntry", "ToolSearchResult"]

@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """Normalized result from an outbound provider tool execution."""

    provider: str
    tool_slug: str
    successful: bool
    data: Any = None
    error: str | None = None
    log_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "tool_slug": self.tool_slug,
            "successful": self.successful,
            "data": self.data,
            "error": self.error,
            "log_id": self.log_id,
        }


@dataclass(frozen=True, slots=True)
class ToolCatalogEntry:
    """One tool row in a provider catalog (no secrets)."""

    slug: str
    name: str
    description: str
    toolkit_slug: str | None = None
    toolkit_name: str | None = None
    version: str | None = None
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "toolkit_slug": self.toolkit_slug,
            "toolkit_name": self.toolkit_name,
            "version": self.version,
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class ToolSearchResult:
    """Result from Composio intent search (COMPOSIO_SEARCH_TOOLS or catalog query)."""

    mode: str
    use_case: str
    tools: tuple[ToolCatalogEntry, ...] = ()
    session_id: str | None = None
    successful: bool = True
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "use_case": self.use_case,
            "successful": self.successful,
            "error": self.error,
            "session_id": self.session_id,
            "tools": [tool.to_dict() for tool in self.tools],
            "count": len(self.tools),
        }


@runtime_checkable
class ProviderAdapter(Protocol):
    """Execute tools for one connector provider implementation."""

    provider_id: str

    def execute_tool(
        self,
        tool_slug: str,
        arguments: dict[str, Any] | None = None,
        *,
        version: str | None = None,
        connected_account_id: str | None = None,
    ) -> ToolCallResult: ...
