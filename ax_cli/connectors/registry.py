"""Connector registry: load, save, and CRUD over ``connectors.json``."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .constants import CONNECTORS_SCHEMA_VERSION, UNSET
from .paths import connectors_registry_path  # re-exported for backward-compatible imports
from .storage import atomic_write_json, read_json_object, utc_now_iso
from .validation import (
    coerce_connectors_registry,
    default_connectors_registry,
    normalize_connector_record,
    validate_connector_record,
)

# Re-export for callers that imported schema version from this module.
__all__ = [
    "CONNECTORS_SCHEMA_VERSION",
    "add_connector",
    "connectors_registry_path",
    "default_connectors_registry",
    "find_connector",
    "list_connectors",
    "load_connectors_registry",
    "normalize_connector_record",
    "remove_connector",
    "save_connectors_registry",
    "update_connector",
    "validate_connector_record",
]


def _connector_rows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    items = registry.get("connectors")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def list_connectors(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a shallow copy of each connector row (safe for JSON serialization)."""
    return [dict(x) for x in _connector_rows(registry)]


def find_connector(registry: dict[str, Any], ref: str) -> dict[str, Any] | None:
    """Return the live row dict from ``registry`` (mutations persist), or None."""
    needle = str(ref or "").strip()
    if not needle:
        return None
    lower = needle.lower()
    for row in _connector_rows(registry):
        if str(row.get("id") or "") == needle:
            return row
        if str(row.get("name") or "").lower() == lower:
            return row
    return None


def assert_unique_connector_name(registry: dict[str, Any], name: str, *, exclude_id: str | None = None) -> None:
    """Raise ``ValueError`` if another connector already uses this name (case-insensitive)."""
    n = str(name or "").strip()
    if not n:
        raise ValueError("name is required")
    eid = str(exclude_id or "").strip()
    for row in _connector_rows(registry):
        rid = str(row.get("id") or "")
        if eid and rid == eid:
            continue
        if str(row.get("name") or "").strip().lower() == n.lower():
            raise ValueError(f"connector name already in use: {row.get('name')!r}")


def load_connectors_registry() -> dict[str, Any]:
    path = connectors_registry_path()
    raw = read_json_object(path, default=default_connectors_registry())
    coerced = coerce_connectors_registry(raw)
    coerced["version"] = CONNECTORS_SCHEMA_VERSION
    return coerced


def save_connectors_registry(registry: dict[str, Any]) -> Path:
    """Validate and atomically persist the registry. Returns the file path."""
    path = connectors_registry_path()
    rows = _connector_rows(registry)
    seen_ids: set[str] = set()
    for row in rows:
        validate_connector_record(row)
        rid = str(row.get("id") or "")
        if rid in seen_ids:
            raise ValueError(f"duplicate connector id: {rid!r}")
        seen_ids.add(rid)
    names = [str(r.get("name") or "").strip().lower() for r in rows]
    if len(names) != len(set(names)):
        raise ValueError("duplicate connector name (case-insensitive)")
    payload = {"version": CONNECTORS_SCHEMA_VERSION, "connectors": rows}
    atomic_write_json(path, payload)
    return path


def add_connector(
    registry: dict[str, Any],
    *,
    name: str,
    provider: str,
    enabled: bool = True,
    auth_ref: str | None = None,
    config: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assert_unique_connector_name(registry, name)
    now = utc_now_iso()
    rec = normalize_connector_record(
        {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "provider": provider.strip().lower(),
            "enabled": enabled,
            "auth_ref": auth_ref,
            "config": dict(config or {}),
            "metadata": dict(metadata or {}),
            "created_at": now,
            "updated_at": now,
        }
    )
    validate_connector_record(rec)
    if not isinstance(registry.get("connectors"), list):
        registry["connectors"] = []
    registry["connectors"].append(rec)
    return rec


def update_connector(
    registry: dict[str, Any],
    ref: str,
    *,
    name: str | None = None,
    provider: str | None = None,
    enabled: bool | None = None,
    auth_ref: Any = UNSET,
    clear_auth_ref: bool = False,
    config: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Patch a connector. Use ``clear_auth_ref=True`` to drop ``auth_ref``."""
    target = find_connector(registry, ref)
    if not target:
        return None
    tid = str(target.get("id") or "")
    changed = False
    if clear_auth_ref and auth_ref is not UNSET:
        raise ValueError("cannot pass both clear_auth_ref and auth_ref")
    if name is not None:
        new_name = str(name).strip()
        assert_unique_connector_name(registry, new_name, exclude_id=tid)
        if str(target.get("name") or "").strip() != new_name:
            target["name"] = new_name
            changed = True
    if provider is not None:
        new_p = str(provider).strip()
        if str(target.get("provider") or "").strip() != new_p:
            target["provider"] = new_p
            changed = True
    if enabled is not None:
        new_e = bool(enabled)
        if bool(target.get("enabled", True)) != new_e:
            changed = True
        target["enabled"] = new_e
    if clear_auth_ref:
        if target.get("auth_ref") is not None:
            changed = True
        target["auth_ref"] = None
    elif auth_ref is not UNSET:
        if auth_ref in (None, ""):
            if target.get("auth_ref") is not None:
                changed = True
            target["auth_ref"] = None
        elif isinstance(auth_ref, str):
            new_val = auth_ref.strip() or None
            if target.get("auth_ref") != new_val:
                changed = True
            target["auth_ref"] = new_val
        else:
            raise ValueError("auth_ref must be a string, empty string, or None")
    if config is not None:
        if not isinstance(config, dict):
            raise ValueError("config must be an object")
        target["config"] = dict(config)
        changed = True
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        target["metadata"] = dict(metadata)
        changed = True
    if changed:
        target["updated_at"] = utc_now_iso()
    validate_connector_record(target)
    return target


def remove_connector(registry: dict[str, Any], ref: str) -> bool:
    needle = str(ref or "").strip()
    if not needle:
        return False
    lower = needle.lower()
    items = registry.setdefault("connectors", [])
    if not isinstance(items, list):
        registry["connectors"] = []
        items = registry["connectors"]
    new_list: list[dict[str, Any]] = []
    removed = False
    for row in items:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "")
        rname = str(row.get("name") or "").strip().lower()
        if rid == needle or rname == lower:
            removed = True
            continue
        new_list.append(row)
    registry["connectors"] = new_list
    return removed
