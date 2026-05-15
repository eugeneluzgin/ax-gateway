"""Validate and normalize connector registry rows."""

from __future__ import annotations

import uuid
from typing import Any

from .constants import (
    CONNECTOR_LABEL_RE,
    CONNECTORS_SCHEMA_VERSION,
    MAX_AUTH_REF_LEN,
    MAX_CONNECTOR_ID_LEN,
)
from .storage import utc_now_iso


def validate_connector_record(rec: dict[str, Any]) -> None:
    """Raise ``ValueError`` with a human-readable message if ``rec`` is invalid."""
    errs: list[str] = []
    if not isinstance(rec, dict):
        raise ValueError("connector row must be an object")
    cid = str(rec.get("id") or "").strip()
    name = str(rec.get("name") or "").strip()
    provider = str(rec.get("provider") or "").strip()
    if not cid:
        errs.append("id is required")
    elif len(cid) > MAX_CONNECTOR_ID_LEN:
        errs.append(f"id must be at most {MAX_CONNECTOR_ID_LEN} characters")
    if not name:
        errs.append("name is required")
    elif not CONNECTOR_LABEL_RE.match(name):
        errs.append("name must be 1–64 chars: start with alphanumeric, then [a-zA-Z0-9_.-]")
    if not provider:
        errs.append("provider is required")
    elif not CONNECTOR_LABEL_RE.match(provider):
        errs.append("provider must be 1–64 chars: start with alphanumeric, then [a-zA-Z0-9_.-]")
    enabled = rec.get("enabled", True)
    if not isinstance(enabled, bool):
        errs.append("enabled must be a boolean")
    auth_ref = rec.get("auth_ref")
    if auth_ref is not None and auth_ref != "":
        if not isinstance(auth_ref, str):
            errs.append("auth_ref must be a string or null")
        elif len(auth_ref) > MAX_AUTH_REF_LEN:
            errs.append(
                f"auth_ref must be at most {MAX_AUTH_REF_LEN} characters "
                "(use a path or opaque ref, not inline secrets)"
            )
    cfg = rec.get("config", {})
    if cfg is None:
        cfg = {}
    if not isinstance(cfg, dict):
        errs.append("config must be an object")
    meta = rec.get("metadata", {})
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        errs.append("metadata must be an object")
    for key in ("created_at", "updated_at"):
        val = rec.get(key)
        if val is not None and val != "" and not isinstance(val, str):
            errs.append(f"{key} must be a string or omitted")
    if errs:
        raise ValueError("; ".join(errs))


def normalize_connector_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict with defaults applied; does not validate beyond coercion."""
    if not isinstance(rec, dict):
        raise ValueError("connector row must be an object")
    cid = str(rec.get("id") or "").strip() or str(uuid.uuid4())
    name = str(rec.get("name") or "").strip()
    provider = str(rec.get("provider") or "").strip()
    enabled = rec.get("enabled", True)
    if not isinstance(enabled, bool):
        enabled = bool(enabled)
    auth_ref_raw = rec.get("auth_ref")
    if auth_ref_raw is None or auth_ref_raw == "":
        auth_ref: str | None = None
    else:
        auth_ref = str(auth_ref_raw).strip() or None
    cfg = rec.get("config") or {}
    if not isinstance(cfg, dict):
        cfg = {}
    meta = rec.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    created = rec.get("created_at")
    updated = rec.get("updated_at")
    return {
        "id": cid,
        "name": name,
        "provider": provider,
        "enabled": enabled,
        "auth_ref": auth_ref,
        "config": dict(cfg),
        "metadata": dict(meta),
        "created_at": str(created) if created else utc_now_iso(),
        "updated_at": str(updated) if updated else utc_now_iso(),
    }


def default_connectors_registry() -> dict[str, Any]:
    return {"version": CONNECTORS_SCHEMA_VERSION, "connectors": []}


def coerce_connectors_registry(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse on-disk JSON into a normalized in-memory registry."""
    version = raw.get("version")
    try:
        v = int(version) if version is not None else CONNECTORS_SCHEMA_VERSION
    except (TypeError, ValueError):
        v = CONNECTORS_SCHEMA_VERSION
    rows_in = raw.get("connectors")
    if rows_in is None:
        rows_in = []
    if not isinstance(rows_in, list):
        rows_in = []
    connectors: list[dict[str, Any]] = []
    for row in rows_in:
        if not isinstance(row, dict):
            continue
        try:
            normalized = normalize_connector_record(row)
            validate_connector_record(normalized)
        except ValueError:
            continue
        connectors.append(normalized)
    return {"version": v, "connectors": connectors}
