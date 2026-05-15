"""Tests for ax_cli.connectors.auth."""

from __future__ import annotations

import json

from ax_cli.connectors.auth import (
    AUTH_REF_MANAGED,
    connectors_auth_env_base,
    delete_managed_auth_file,
    ensure_managed_auth_file,
    load_connector_auth_env,
    parse_dotenv,
    public_auth_status,
    release_managed_auth_if_unused,
    resolve_auth_env_path,
    uses_managed_auth,
    write_managed_auth_from_file,
)
from ax_cli.connectors.registry import (
    add_connector,
    find_connector,
    load_connectors_registry,
    remove_connector,
    save_connectors_registry,
    update_connector,
)


def test_parse_dotenv_basic():
    text = """
# c
export FOO=bar
BAZ='quoted'
"""
    d = parse_dotenv(text)
    assert d["FOO"] == "bar"
    assert d["BAZ"] == "quoted"


def test_managed_path_and_load(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    cid = "test-connector-id-001"
    p = ensure_managed_auth_file(cid)
    assert p.parent == connectors_auth_env_base()
    assert p.name == f"{cid}.env"
    p.write_text("API_KEY=secret-value\n", encoding="utf-8")
    row = {"id": cid, "auth_ref": AUTH_REF_MANAGED}
    env = load_connector_auth_env(row)
    assert env.get("API_KEY") == "secret-value"


def test_public_auth_status_never_contains_values(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    cid = "uuid-here-0000"
    ensure_managed_auth_file(cid)
    env_path = connectors_auth_env_base() / f"{cid}.env"
    env_path.write_text("TOKEN=supersecret\n", encoding="utf-8")
    st = public_auth_status({"id": cid, "auth_ref": AUTH_REF_MANAGED})
    dumped = json.dumps(st)
    assert "supersecret" not in dumped
    assert "TOKEN" in st.get("env_keys", [])


def test_release_managed_auth_if_unused(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    cid = "rel-001"
    ensure_managed_auth_file(cid)
    env_path = connectors_auth_env_base() / f"{cid}.env"
    assert env_path.is_file()
    release_managed_auth_if_unused({"id": cid, "auth_ref": AUTH_REF_MANAGED}, auth_ref_after=None)
    assert not env_path.is_file()


def test_release_keeps_file_when_still_managed(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    cid = "rel-002"
    ensure_managed_auth_file(cid)
    env_path = connectors_auth_env_base() / f"{cid}.env"
    release_managed_auth_if_unused({"id": cid, "auth_ref": AUTH_REF_MANAGED}, auth_ref_after=AUTH_REF_MANAGED)
    assert env_path.is_file()


def test_write_managed_auth_from_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    src = tmp_path / "src.env"
    src.write_text("X=1\n", encoding="utf-8")
    cid = "write-001"
    dest = write_managed_auth_from_file(cid, src)
    assert dest.is_file()
    assert load_connector_auth_env({"id": cid, "auth_ref": AUTH_REF_MANAGED})["X"] == "1"


def test_resolve_external_path(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    ext = tmp_path / "external.env"
    ext.write_text("Y=2\n", encoding="utf-8")
    row = {"id": "x", "auth_ref": str(ext)}
    assert resolve_auth_env_path(row) == ext.resolve()
    assert load_connector_auth_env(row)["Y"] == "2"


def test_remove_connector_deletes_managed_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = load_connectors_registry()
    rec = add_connector(reg, name="m", provider="p", auth_ref=AUTH_REF_MANAGED)
    save_connectors_registry(reg)
    cid = str(rec["id"])
    ensure_managed_auth_file(cid)
    env_path = connectors_auth_env_base() / f"{cid}.env"
    assert env_path.is_file()
    assert remove_connector(reg, "m") is True
    save_connectors_registry(reg)
    if uses_managed_auth({"id": cid, "auth_ref": AUTH_REF_MANAGED}):
        delete_managed_auth_file(cid)
    assert not env_path.is_file()


def test_update_clear_auth_releases_managed(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = load_connectors_registry()
    rec = add_connector(reg, name="u", provider="p", auth_ref=AUTH_REF_MANAGED)
    save_connectors_registry(reg)
    cid = str(rec["id"])
    ensure_managed_auth_file(cid)
    env_path = connectors_auth_env_base() / f"{cid}.env"
    row = find_connector(reg, "u")
    assert row is not None
    snap = {"id": cid, "auth_ref": row.get("auth_ref")}
    update_connector(reg, "u", clear_auth_ref=True)
    save_connectors_registry(reg)
    row2 = find_connector(reg, "u")
    assert row2 is not None
    release_managed_auth_if_unused(snap, auth_ref_after=str(row2.get("auth_ref") or "").strip() or None)
    assert not env_path.is_file()
