"""Filesystem-backed connector registry for the local Gateway.

Each row describes an outbound integration (e.g. Composio MCP, custom HTTP MCP).
Secrets must not live inline: use ``auth_ref`` for a path or vault key only.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ax_cli.gateway import gateway_dir

CONNECTORS_SCHEMA_VERSION = 1

# Slug-safe labels for operator UX and future dashboard/API use.
_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$", re.IGNORECASE)

_MAX_AUTH_REF_LEN = 2048
_MAX_ID_LEN = 128


class _UnsetType:
    __slots__ = ()


_UNSET: Any = _UnsetType()


def connectors_registry_path() -> Path:
    return gateway_dir() / "connectors.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_connectors_registry() -> dict[str, Any]:
    return {"version": CONNECTORS_SCHEMA_VERSION, "connectors": []}


def _atomic_write_json(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(payload, tmp, indent=2, sort_keys=True)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        assert tmp_path is not None
        tmp_path.chmod(mode)
        tmp_path.replace(path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    try:
        path.chmod(mode)
    except OSError:
        pass


def _read_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        return copy.deepcopy(default_connectors_registry())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copy.deepcopy(default_connectors_registry())
    if not isinstance(raw, dict):
        return copy.deepcopy(default_connectors_registry())
    return raw


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
    elif len(cid) > _MAX_ID_LEN:
        errs.append(f"id must be at most {_MAX_ID_LEN} characters")
    if not name:
        errs.append("name is required")
    elif not _LABEL_RE.match(name):
        errs.append("name must be 1–64 chars: start with alphanumeric, then [a-zA-Z0-9_.-]")
    if not provider:
        errs.append("provider is required")
    elif not _LABEL_RE.match(provider):
        errs.append("provider must be 1–64 chars: start with alphanumeric, then [a-zA-Z0-9_.-]")
    enabled = rec.get("enabled", True)
    if not isinstance(enabled, bool):
        errs.append("enabled must be a boolean")
    auth_ref = rec.get("auth_ref")
    if auth_ref is not None and auth_ref != "":
        if not isinstance(auth_ref, str):
            errs.append("auth_ref must be a string or null")
        elif len(auth_ref) > _MAX_AUTH_REF_LEN:
            errs.append(
                f"auth_ref must be at most {_MAX_AUTH_REF_LEN} characters (use a path or opaque ref, not inline secrets)"
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
        "created_at": str(created) if created else _now_iso(),
        "updated_at": str(updated) if updated else _now_iso(),
    }


def _connector_rows(registry: dict[str, Any]) -> list[dict[str, Any]]:
    items = registry.get("connectors")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def _coerce_registry(raw: dict[str, Any]) -> dict[str, Any]:
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
    raw = _read_raw(path)
    coerced = _coerce_registry(raw)
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
    _atomic_write_json(path, payload)
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
    now = _now_iso()
    rec = normalize_connector_record(
        {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "provider": provider.strip(),
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
    auth_ref: Any = _UNSET,
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
    if clear_auth_ref and auth_ref is not _UNSET:
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
    elif auth_ref is not _UNSET:
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
        target["updated_at"] = _now_iso()
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
