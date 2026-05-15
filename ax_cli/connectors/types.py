"""Typed shapes for connector registry data (documentation and static checking)."""

from __future__ import annotations

from typing import Any, TypedDict


class ConnectorRecord(TypedDict, total=False):
    """One row in ``connectors.json`` — secrets belong in auth env files, not here."""

    id: str
    name: str
    provider: str
    enabled: bool
    auth_ref: str | None
    config: dict[str, Any]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class ConnectorRegistry(TypedDict):
    version: int
    connectors: list[ConnectorRecord]
