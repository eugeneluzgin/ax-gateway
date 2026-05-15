"""Filesystem paths for connector registry and auth (scoped under the Gateway dir)."""

from __future__ import annotations

from pathlib import Path

from ax_cli.gateway import gateway_dir


def connectors_registry_path() -> Path:
    """``connectors.json`` — connector rows and non-secret config only."""
    return gateway_dir() / "connectors.json"


def connectors_auth_env_base() -> Path:
    """Directory for per-connector ``*.env`` secret files (may not exist yet)."""
    return gateway_dir() / "connectors" / "auth"
