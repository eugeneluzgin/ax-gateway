"""Shared types for connector provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class ConnectorProviderError(RuntimeError):
    """Raised when a connector cannot run a provider tool (config, auth, or API)."""


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
