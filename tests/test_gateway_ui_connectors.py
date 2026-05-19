"""Gateway operator UI: connectors API and dashboard shell."""

from __future__ import annotations

import json
import socket
import threading
from contextlib import closing

import httpx

from ax_cli import gateway as gateway_core
from ax_cli.commands import gateway as gateway_cmd
from ax_cli.connectors import AUTH_REF_MANAGED, add_connector, load_connectors_registry, save_connectors_registry


def test_render_gateway_ui_page_includes_connectors_panel():
    page = gateway_cmd._render_gateway_ui_page(refresh_ms=2000)
    assert "Outbound Connectors" in page
    assert "/api/connectors" in page
    assert "connector-rows" in page
    assert "add-connector-form" in page
    assert "renderConnectors" in page
    assert "populateConnectorProviderSelect" in page
    assert "connector-base-url" in page


def test_connectors_providers_api_payload():
    payload = gateway_cmd.providers_payload()
    ids = {row["id"] for row in payload["providers"]}
    assert "composio" in ids
    assert "http_mcp" in ids


def test_connectors_list_payload_includes_provider_catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    payload = gateway_cmd._connectors_list_payload()
    catalog = payload.get("provider_catalog") or []
    assert any(row.get("id") == "http_mcp" for row in catalog)


def test_connectors_list_payload_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = load_connectors_registry()
    add_connector(
        reg,
        name="ui_conn",
        provider="composio",
        auth_ref=AUTH_REF_MANAGED,
        config={"user_id": "ent-1", "allowed_tools": ["GITHUB_*"]},
    )
    save_connectors_registry(reg)
    (tmp_path / "connectors" / "auth").mkdir(parents=True, exist_ok=True)
    row = reg["connectors"][0]
    (tmp_path / "connectors" / "auth" / f"{row['id']}.env").write_text(
        "COMPOSIO_API_KEY=secret-value\n",
        encoding="utf-8",
    )
    payload = gateway_cmd._connectors_list_payload()
    assert payload["count"] == 1
    summary = payload["connectors"][0]
    assert summary["name"] == "ui_conn"
    assert "secret" not in json.dumps(payload)
    assert summary["auth_env_keys"] == ["COMPOSIO_API_KEY"]


def test_gateway_ui_connectors_api_crud(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    monkeypatch.setattr(gateway_core, "_scan_gateway_process_pids", lambda: [])
    monkeypatch.setattr(gateway_core, "_scan_gateway_ui_process_pids", lambda: [])

    handler = gateway_cmd._build_gateway_ui_handler(activity_limit=5, refresh_ms=1500)
    with closing(socket.socket()) as probe:
        probe.bind(("127.0.0.1", 0))
        host, port = probe.getsockname()
    server = gateway_cmd._GatewayUiServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://{host}:{port}", timeout=2.0) as client:
            created = client.post(
                "/api/connectors",
                json={
                    "name": "dash_composio",
                    "provider": "composio",
                    "managed_auth": True,
                    "config": {"user_id": "u1", "allowed_tools": ["GITHUB_*"]},
                },
            )
            assert created.status_code == 201
            assert created.json()["connector"]["name"] == "dash_composio"
            assert "secret" not in created.text

            listing = client.get("/api/connectors")
            assert listing.status_code == 200
            assert listing.json()["count"] == 1

            status = client.get("/api/status")
            assert status.status_code == 200
            body = status.json()
            assert body["summary"]["connectors"] == 1
            assert len(body["connectors"]) == 1
            providers = client.get("/api/connectors/providers")
            assert providers.status_code == 200
            provider_ids = {row["id"] for row in providers.json().get("providers", [])}
            assert "http_mcp" in provider_ids

            updated = client.put(
                "/api/connectors/dash_composio",
                json={"enabled": False},
            )
            assert updated.status_code == 200
            assert updated.json()["summary"]["enabled"] is False

            removed = client.delete("/api/connectors/dash_composio")
            assert removed.status_code == 200
            assert client.get("/api/connectors").json()["count"] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_status_payload_includes_connectors_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = load_connectors_registry()
    add_connector(reg, name="c1", provider="composio", enabled=True)
    save_connectors_registry(reg)
    gateway_core.save_gateway_registry({"agents": [], "gateway": {"gateway_id": "gw-test"}})
    monkeypatch.setattr(gateway_cmd, "daemon_status", lambda: {"running": False, "pid": None, "registry": {"agents": [], "gateway": {}}})
    monkeypatch.setattr(gateway_cmd, "ui_status", lambda: {"running": False, "pid": None, "host": "127.0.0.1", "port": 8765, "url": "", "log_path": ""})
    monkeypatch.setattr(gateway_cmd, "load_gateway_session", lambda: None)
    payload = gateway_cmd._status_payload()
    assert payload["summary"]["connectors"] == 1
    assert payload["connectors_summary"]["total"] == 1
    assert any(row.get("id") == "composio" for row in payload.get("connector_providers") or [])
