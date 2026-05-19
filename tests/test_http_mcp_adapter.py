"""Tests for HTTP MCP provider adapter and multi-provider dispatch."""

from __future__ import annotations

import json

import httpx
import pytest

from ax_cli.connectors.auth import AUTH_REF_MANAGED, ensure_managed_auth_file
from ax_cli.connectors.providers.base import ConnectorProviderError
from ax_cli.connectors.providers.catalog import SUPPORTED_PROVIDERS, providers_payload
from ax_cli.connectors.providers.dispatch import (
    adapter_for_connector,
    execute_connector_tool,
    list_connector_tools,
    search_connector_tools,
)
from ax_cli.connectors.providers.http_mcp_adapter import (
    HttpMcpAdapter,
    build_http_mcp_adapter,
    resolve_http_mcp_settings,
)
from ax_cli.connectors.registry import add_connector, load_connectors_registry, save_connectors_registry
from ax_cli.connectors.validation import validate_connector_record


def test_providers_payload_includes_composio_and_http_mcp():
    payload = providers_payload()
    ids = {row["id"] for row in payload["providers"]}
    assert ids == set(SUPPORTED_PROVIDERS)
    composio = next(row for row in payload["providers"] if row["id"] == "composio")
    http_mcp = next(row for row in payload["providers"] if row["id"] == "http_mcp")
    assert composio["supports_intent_search"] is True
    assert http_mcp["supports_intent_search"] is False
    assert http_mcp["supports_list_tools"] is True


def test_validate_rejects_unsupported_provider():
    with pytest.raises(ValueError, match="unsupported provider"):
        validate_connector_record(
            {
                "id": "id1",
                "name": "demo",
                "provider": "unknown_vendor",
                "enabled": True,
                "config": {},
                "metadata": {},
            }
        )


def test_validate_http_mcp_requires_base_url():
    with pytest.raises(ValueError, match="base_url"):
        validate_connector_record(
            {
                "id": "id1",
                "name": "mcp_demo",
                "provider": "http_mcp",
                "enabled": True,
                "config": {},
                "metadata": {},
            }
        )


def test_resolve_http_mcp_settings_from_config_and_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    connector = {
        "id": "mcp-1",
        "name": "mcp",
        "provider": "http_mcp",
        "enabled": True,
        "auth_ref": AUTH_REF_MANAGED,
        "config": {"base_url": "https://mcp.example.com/rpc"},
    }
    ensure_managed_auth_file("mcp-1")
    env_path = tmp_path / "connectors" / "auth" / "mcp-1.env"
    env_path.write_text("MCP_BEARER_TOKEN=secret-token\n", encoding="utf-8")
    settings = resolve_http_mcp_settings(connector)
    assert settings["base_url"] == "https://mcp.example.com/rpc"
    adapter = build_http_mcp_adapter(connector)
    assert "Bearer secret-token" in adapter._headers.get("Authorization", "")


def test_http_mcp_adapter_list_and_execute():
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        calls.append(body)
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}})
        if method == "notifications/initialized":
            return httpx.Response(200, json={})
        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "echo",
                                "description": "Echo input",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                },
            )
        if method == "tools/call":
            assert body["params"]["name"] == "echo"
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"content": [{"type": "text", "text": "ok"}], "isError": False},
                },
            )
        return httpx.Response(400, json={"error": "unexpected"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://mcp.example.com")
    adapter = HttpMcpAdapter(
        base_url="https://mcp.example.com/rpc",
        headers={"Content-Type": "application/json"},
        skip_initialize=False,
        client=client,
    )
    tools = adapter.list_tools_raw()
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"
    result = adapter.execute_tool("echo", {"message": "hi"})
    assert result.successful is True
    assert any(c.get("method") == "tools/call" for c in calls)


def test_dispatch_list_and_search_http_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}})
        if method == "notifications/initialized":
            return httpx.Response(200, json={})
        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"tools": [{"name": "ping", "description": "Ping tool"}]},
                },
            )
        return httpx.Response(400, json={})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        return real_client(transport=transport, base_url="https://mcp.test")

    monkeypatch.setattr(
        "ax_cli.connectors.providers.http_mcp_adapter.httpx.Client",
        client_factory,
    )

    reg = load_connectors_registry()
    rec = add_connector(
        reg,
        name="local_mcp",
        provider="http_mcp",
        auth_ref=AUTH_REF_MANAGED,
        config={"base_url": "https://mcp.test/rpc", "skip_initialize": True},
    )
    save_connectors_registry(reg)
    ensure_managed_auth_file(str(rec["id"]))

    page = list_connector_tools("local_mcp")
    assert page["provider"] == "http_mcp"
    assert page["count"] == 1
    assert page["tools"][0]["slug"] == "ping"

    search = search_connector_tools("local_mcp", "ping")
    assert search.mode == "catalog"
    assert len(search.tools) == 1


def test_adapter_for_connector_rejects_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    connector = {
        "id": "x",
        "name": "x",
        "provider": "http_mcp",
        "enabled": False,
        "config": {"base_url": "https://mcp.test"},
    }
    with pytest.raises(ConnectorProviderError, match="disabled"):
        adapter_for_connector(connector)
