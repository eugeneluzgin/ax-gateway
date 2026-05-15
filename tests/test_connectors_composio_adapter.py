"""Tests for Composio provider adapter and connector tool dispatch."""

from __future__ import annotations

import json

import httpx
import pytest

from ax_cli.connectors.auth import AUTH_REF_MANAGED, ensure_managed_auth_file
from ax_cli.connectors.providers.base import ConnectorProviderError
from ax_cli.connectors.providers.composio_adapter import (
    ComposioAdapter,
    build_composio_adapter,
    resolve_composio_settings,
)
from ax_cli.connectors.providers.dispatch import adapter_for_connector, execute_connector_tool
from ax_cli.connectors.registry import add_connector, load_connectors_registry, save_connectors_registry


def test_resolve_composio_settings_from_config_and_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    connector = {
        "id": "cid-1",
        "name": "c",
        "provider": "composio",
        "enabled": True,
        "auth_ref": AUTH_REF_MANAGED,
        "config": {"user_id": "user-abc", "base_url": "https://example.test"},
    }
    ensure_managed_auth_file("cid-1")
    env_path = tmp_path / "connectors" / "auth" / "cid-1.env"
    env_path.write_text("COMPOSIO_API_KEY=sk-test\n", encoding="utf-8")
    settings = resolve_composio_settings(connector)
    assert settings["api_key"] == "sk-test"
    assert settings["user_id"] == "user-abc"
    assert settings["base_url"] == "https://example.test"


def test_resolve_composio_settings_missing_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    connector = {
        "id": "cid-2",
        "name": "c",
        "provider": "composio",
        "enabled": True,
        "auth_ref": AUTH_REF_MANAGED,
        "config": {"user_id": "u"},
    }
    ensure_managed_auth_file("cid-2")
    with pytest.raises(ConnectorProviderError, match="API key"):
        resolve_composio_settings(connector)


def test_composio_adapter_execute_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v3/tools/execute/GITHUB_LIST_STARGAZERS"
        assert request.headers["x-api-key"] == "sk-test"
        body = json.loads(request.content.decode())
        assert body["user_id"] == "user-1"
        assert body["arguments"]["owner"] == "ComposioHQ"
        return httpx.Response(
            200,
            json={"successful": True, "data": {"items": []}, "error": None, "log_id": "log_1"},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://backend.composio.dev")
    adapter = ComposioAdapter(
        api_key="sk-test",
        user_id="user-1",
        base_url="https://backend.composio.dev",
        client=client,
    )
    result = adapter.execute_tool(
        "GITHUB_LIST_STARGAZERS",
        {"owner": "ComposioHQ", "repo": "composio"},
    )
    assert result.successful is True
    assert result.data == {"items": []}
    assert result.log_id == "log_1"
    assert result.error is None


def test_composio_adapter_execute_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid api key", "successful": False})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://backend.composio.dev")
    adapter = ComposioAdapter(
        api_key="bad",
        user_id="user-1",
        base_url="https://backend.composio.dev",
        client=client,
    )
    result = adapter.execute_tool("SOME_TOOL", {})
    assert result.successful is False
    assert "invalid api key" in (result.error or "")


def test_execute_connector_tool_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = load_connectors_registry()
    rec = add_connector(
        reg,
        name="my_composio",
        provider="composio",
        auth_ref=AUTH_REF_MANAGED,
        config={"user_id": "gateway-agent-1"},
    )
    save_connectors_registry(reg)
    ensure_managed_auth_file(str(rec["id"]))
    env_path = tmp_path / "connectors" / "auth" / f"{rec['id']}.env"
    env_path.write_text("COMPOSIO_API_KEY=sk-e2e\n", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"successful": True, "data": {"ok": True}, "error": None},
        )

    transport = httpx.MockTransport(handler)
    mock_client = httpx.Client(transport=transport, base_url="https://backend.composio.dev")

    def _factory(connector: dict) -> ComposioAdapter:
        settings = resolve_composio_settings(connector)
        return ComposioAdapter(
            api_key=settings["api_key"],
            user_id=settings["user_id"],
            base_url=settings["base_url"],
            client=mock_client,
        )

    from ax_cli.connectors.providers import registry as provider_registry

    monkeypatch.setitem(provider_registry._FACTORIES, "composio", _factory)
    result = execute_connector_tool("my_composio", "ECHO_TOOL", {"x": 1})
    assert result.successful is True
    assert result.data == {"ok": True}


def test_adapter_for_connector_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    connector = {
        "id": "x",
        "name": "off",
        "provider": "composio",
        "enabled": False,
        "config": {"user_id": "u"},
    }
    with pytest.raises(ConnectorProviderError, match="disabled"):
        adapter_for_connector(connector)


def test_build_composio_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    connector = {
        "id": "b1",
        "name": "c",
        "provider": "composio",
        "enabled": True,
        "auth_ref": AUTH_REF_MANAGED,
        "config": {"user_id": "u1"},
    }
    ensure_managed_auth_file("b1")
    (tmp_path / "connectors" / "auth" / "b1.env").write_text("COMPOSIO_API_KEY=k\n", encoding="utf-8")
    adapter = build_composio_adapter(connector)
    assert adapter.provider_id == "composio"
