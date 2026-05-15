"""Provider id → adapter factory."""

from __future__ import annotations

from typing import Any, Callable

from .base import ConnectorProviderError, ProviderAdapter
from .composio_adapter import build_composio_adapter

ProviderFactory = Callable[[dict[str, Any]], ProviderAdapter]

SUPPORTED_PROVIDERS: frozenset[str] = frozenset({"composio"})

_FACTORIES: dict[str, ProviderFactory] = {
    "composio": build_composio_adapter,
}


def get_provider_adapter(provider_id: str, connector: dict[str, Any]) -> ProviderAdapter:
    """Instantiate the adapter for ``provider_id`` using ``connector`` row + auth env."""
    pid = str(provider_id or "").strip().lower()
    factory = _FACTORIES.get(pid)
    if factory is None:
        raise ConnectorProviderError(
            f"unsupported connector provider {provider_id!r} (supported: {', '.join(sorted(SUPPORTED_PROVIDERS))})"
        )
    return factory(connector)
