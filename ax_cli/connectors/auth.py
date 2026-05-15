"""Gateway-managed and file-backed connector auth (secrets never in ``connectors.json``)."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ax_cli.gateway import _chmod_quiet, _redacted_path

from .constants import AUTH_REF_MANAGED, CONNECTOR_ID_FILENAME_RE, FILE_MODE_DIR, FILE_MODE_SECRET
from .envfile import parse_dotenv
from .paths import connectors_auth_env_base

__all__ = [
    "AUTH_REF_MANAGED",
    "connectors_auth_env_base",
    "delete_managed_auth_file",
    "ensure_connectors_auth_env_dir",
    "ensure_managed_auth_file",
    "load_connector_auth_env",
    "parse_dotenv",
    "public_auth_status",
    "release_managed_auth_if_unused",
    "resolve_auth_env_path",
    "uses_managed_auth",
    "write_managed_auth_from_file",
]


def ensure_connectors_auth_env_dir() -> Path:
    """Ensure the auth directory exists with restrictive permissions."""
    path = connectors_auth_env_base()
    path.mkdir(parents=True, exist_ok=True)
    _chmod_quiet(path, FILE_MODE_DIR)
    return path


def _managed_env_path(connector_id: str) -> Path:
    cid = str(connector_id or "").strip()
    if not CONNECTOR_ID_FILENAME_RE.match(cid):
        raise ValueError("connector id is not usable as a managed auth filename")
    return connectors_auth_env_base() / f"{cid}.env"


def uses_managed_auth(connector: dict[str, Any] | None) -> bool:
    if not isinstance(connector, dict):
        return False
    return str(connector.get("auth_ref") or "").strip() == AUTH_REF_MANAGED


def resolve_auth_env_path(connector: dict[str, Any]) -> Path | None:
    """Resolve the env file path for this connector, or None if unconfigured."""
    if not isinstance(connector, dict):
        return None
    ref = str(connector.get("auth_ref") or "").strip()
    if not ref:
        return None
    if ref == AUTH_REF_MANAGED:
        cid = str(connector.get("id") or "").strip()
        if not cid:
            return None
        return _managed_env_path(cid)
    path = Path(ref).expanduser()
    try:
        return path.resolve()
    except OSError:
        return path


def ensure_managed_auth_file(connector_id: str) -> Path:
    """Create an empty managed ``.env`` if missing."""
    ensure_connectors_auth_env_dir()
    path = _managed_env_path(connector_id)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _chmod_quiet(path.parent, FILE_MODE_DIR)
        path.write_text("# Connector secrets (KEY=VALUE). Do not commit.\n", encoding="utf-8")
    _chmod_quiet(path, FILE_MODE_SECRET)
    return path


def delete_managed_auth_file(connector_id: str) -> bool:
    """Remove the managed env file if it exists. Returns whether a file was removed."""
    try:
        path = _managed_env_path(connector_id)
    except ValueError:
        return False
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def write_managed_auth_from_file(connector_id: str, source: Path) -> Path:
    """Atomically replace managed env content with a copy of ``source``."""
    src = source.expanduser()
    if not src.is_file():
        raise ValueError(f"source is not a file: {src}")
    dest = _managed_env_path(connector_id)
    ensure_connectors_auth_env_dir()
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=dest.parent,
            prefix=f".{dest.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            with src.open("rb") as handle:
                shutil.copyfileobj(handle, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
        assert tmp_path is not None
        tmp_path.chmod(FILE_MODE_SECRET)
        tmp_path.replace(dest)
    finally:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    _chmod_quiet(dest, FILE_MODE_SECRET)
    return dest


def load_connector_auth_env(connector: dict[str, Any]) -> dict[str, str]:
    """Load env entries from the connector's auth file. Values are sensitive — do not log."""
    path = resolve_auth_env_path(connector)
    if path is None:
        return {}
    try:
        if not path.is_file():
            return {}
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return parse_dotenv(text)


def public_auth_status(connector: dict[str, Any]) -> dict[str, Any]:
    """Operator-safe summary: no secret values, only paths (redacted) and key names."""
    ref = str(connector.get("auth_ref") or "").strip() if isinstance(connector, dict) else ""
    if not ref:
        return {"kind": "none", "path_redacted": None, "env_keys": [], "file_exists": False, "error": None}
    path = resolve_auth_env_path(connector) if isinstance(connector, dict) else None
    kind = "managed" if ref == AUTH_REF_MANAGED else "file"
    if path is None:
        return {
            "kind": kind,
            "path_redacted": None,
            "env_keys": [],
            "file_exists": False,
            "error": "auth_ref is set but path could not be resolved",
        }
    redacted = _redacted_path(str(path))
    exists = False
    keys: list[str] = []
    err: str | None = None
    try:
        exists = path.is_file()
        if exists:
            keys = sorted(parse_dotenv(path.read_text(encoding="utf-8")).keys())
    except OSError as exc:
        err = str(exc)
    return {
        "kind": kind,
        "path_redacted": redacted,
        "env_keys": keys,
        "file_exists": exists,
        "error": err,
    }


def release_managed_auth_if_unused(connector_before: dict[str, Any], *, auth_ref_after: str | None) -> None:
    """If we are leaving managed auth, delete the managed secret file (best-effort)."""
    if not uses_managed_auth(connector_before):
        return
    after = str(auth_ref_after or "").strip()
    if after == AUTH_REF_MANAGED:
        return
    cid = str(connector_before.get("id") or "").strip()
    if cid:
        delete_managed_auth_file(cid)
