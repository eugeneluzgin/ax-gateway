"""Tests for ax_cli.connectors.registry."""

from __future__ import annotations

import json

import pytest

from ax_cli.connectors import registry as cr


def test_connectors_registry_path_respects_ax_gateway_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    p = cr.connectors_registry_path()
    assert p == tmp_path / "connectors.json"


def test_add_list_save_load(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = cr.load_connectors_registry()
    cr.add_connector(
        reg,
        name="demo",
        provider="composio",
        auth_ref=str(tmp_path / "composio.env"),
        config={"mcp_server_id": "srv_1"},
    )
    path = cr.save_connectors_registry(reg)
    assert path == tmp_path / "connectors.json"
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == cr.CONNECTORS_SCHEMA_VERSION
    assert len(raw["connectors"]) == 1
    reg2 = cr.load_connectors_registry()
    rows = cr.list_connectors(reg2)
    assert len(rows) == 1
    assert rows[0]["name"] == "demo"
    assert rows[0]["provider"] == "composio"
    assert rows[0]["config"]["mcp_server_id"] == "srv_1"


def test_duplicate_name_in_memory_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = cr.load_connectors_registry()
    cr.add_connector(reg, name="alpha", provider="composio")
    with pytest.raises(ValueError, match="already in use"):
        cr.add_connector(reg, name="ALPHA", provider="composio")


def test_save_rejects_duplicate_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = cr.load_connectors_registry()
    reg.setdefault("connectors", []).append(
        cr.normalize_connector_record({"id": "same", "name": "n1", "provider": "composio"})
    )
    reg["connectors"].append(cr.normalize_connector_record({"id": "same", "name": "n2", "provider": "composio"}))
    with pytest.raises(ValueError, match="duplicate connector id"):
        cr.save_connectors_registry(reg)


def test_find_and_remove(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = cr.load_connectors_registry()
    rec = cr.add_connector(reg, name="x", provider="composio")
    cid = str(rec["id"])
    assert cr.find_connector(reg, "x") is rec
    assert cr.find_connector(reg, cid) is rec
    assert cr.remove_connector(reg, cid) is True
    cr.save_connectors_registry(reg)
    reg3 = cr.load_connectors_registry()
    assert cr.list_connectors(reg3) == []


def test_update_rename_and_disable(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = cr.load_connectors_registry()
    cr.add_connector(reg, name="orig", provider="composio")
    cr.save_connectors_registry(reg)
    reg = cr.load_connectors_registry()
    row = cr.find_connector(reg, "orig")
    assert row is not None
    cr.update_connector(reg, "orig", name="renamed", enabled=False)
    cr.save_connectors_registry(reg)
    reg2 = cr.load_connectors_registry()
    assert cr.find_connector(reg2, "orig") is None
    r2 = cr.find_connector(reg2, "renamed")
    assert r2 is not None
    assert r2["enabled"] is False


def test_validate_rejects_bad_name():
    with pytest.raises(ValueError, match="name"):
        cr.validate_connector_record(
            {
                "id": "id1",
                "name": "bad name!",
                "provider": "p",
                "enabled": True,
                "config": {},
                "metadata": {},
            }
        )


def test_clear_auth_ref(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = cr.load_connectors_registry()
    cr.add_connector(reg, name="c", provider="composio", auth_ref="/tmp/x.env")
    cr.update_connector(reg, "c", clear_auth_ref=True)
    assert cr.find_connector(reg, "c")["auth_ref"] is None
