"""Shared connector-layer exceptions (no provider imports)."""


class ConnectorProviderError(RuntimeError):
    """Raised when a connector cannot run a provider tool (config, auth, or API)."""
