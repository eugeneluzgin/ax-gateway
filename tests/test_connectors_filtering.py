"""Tests for connector tool filtering policy and Composio catalog APIs."""

from __future__ import annotations

import json

import httpx
import pytest

from ax_cli.connectors.auth import AUTH_REF_MANAGED
from ax_cli.connectors.errors import ConnectorProviderError
from ax_cli.connectors.filtering import is_tool_allowed, resolve_tool_filter_policy
from ax_cli.connectors.providers.composio_adapter import ComposioAdapter
from ax_cli.connectors.providers.composio_catalog import list_composio_tools, search_composio_tools_intent
from ax_cli.connectors.providers.dispatch import execute_connector_tool, list_connector_tools
from ax_cli.connectors.registry import add_connector, load_connectors_registry, save_connectors_registry


def test_policy_allow_deny_patterns():
    policy = resolve_tool_filter_policy(
        {
            "config": {
                "allowed_tools": ["GITHUB_*"],
                "denied_tools": ["*_DELETE_*"],
            }
        }
    )
    assert is_tool_allowed("GITHUB_LIST_ISSUES", policy)
    assert not is_tool_allowed("SLACK_SEND_MESSAGE", policy)
    assert not is_tool_allowed("GITHUB_DELETE_ISSUE", policy)


def test_list_composio_tools_with_query():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/api/v3.1/tools" in request.url.path
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "slug": "GITHUB_LIST_STARGAZERS",
                        "name": "List Stargazers",
                        "description": "List stargazers",
                        "toolkit": {"slug": "github", "name": "GitHub"},
                        "version": "latest",
                        "tags": [],
                    },
                    {
                        "slug": "SLACK_SEND_MESSAGE",
                        "name": "Send",
                        "description": "Send slack",
                        "toolkit": {"slug": "slack", "name": "Slack"},
                        "version": "latest",
                        "tags": [],
                    },
                ],
                "total_items": 2,
                "next_cursor": None,
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://backend.composio.dev")
    adapter = ComposioAdapter(api_key="k", user_id="u", base_url="https://backend.composio.dev", client=client)
    policy = resolve_tool_filter_policy({"config": {"allowed_tools": ["GITHUB_*"]}})
    page = list_composio_tools(adapter, policy, query="stars")
    assert page["count"] == 1
    assert page["tools"][0]["slug"] == "GITHUB_LIST_STARGAZERS"


def test_search_composio_tools_intent_parses_slugs():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"items": []})
        body = json.loads(request.content.decode())
        assert body["arguments"]["queries"][0]["use_case"] == "send github stars list"
        return httpx.Response(
            200,
            json={
                "successful": True,
                "data": {
                    "session": {"id": "sess-abc"},
                    "tools": [{"tool_slug": "GITHUB_LIST_STARGAZERS"}, {"tool_slug": "SLACK_SEND_MESSAGE"}],
                },
                "error": None,
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://backend.composio.dev")
    adapter = ComposioAdapter(api_key="k", user_id="u", base_url="https://backend.composio.dev", client=client)
    policy = resolve_tool_filter_policy({"config": {"allowed_tools": ["GITHUB_*"]}})
    result = search_composio_tools_intent(adapter, policy, "send github stars list")
    assert result.successful is True
    assert result.session_id == "sess-abc"
    assert len(result.tools) == 1
    assert result.tools[0].slug == "GITHUB_LIST_STARGAZERS"


def test_execute_blocked_by_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = load_connectors_registry()
    add_connector(
        reg,
        name="filt",
        provider="composio",
        auth_ref=AUTH_REF_MANAGED,
        config={"user_id": "u", "allowed_tools": ["GITHUB_*"]},
    )
    save_connectors_registry(reg)
    with pytest.raises(ConnectorProviderError, match="not allowed"):
        execute_connector_tool("filt", "SLACK_SEND_MESSAGE", {}, record_activity=False)


def test_list_connector_tools_integration(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = load_connectors_registry()
    rec = add_connector(
        reg,
        name="list_me",
        provider="composio",
        auth_ref=AUTH_REF_MANAGED,
        config={"user_id": "u", "toolkits": ["github"]},
    )
    save_connectors_registry(reg)
    (tmp_path / "connectors" / "auth").mkdir(parents=True, exist_ok=True)
    (tmp_path / "connectors" / "auth" / f"{rec['id']}.env").write_text("COMPOSIO_API_KEY=k\n", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "slug": "GITHUB_LIST_STARGAZERS",
                        "name": "List",
                        "description": "d",
                        "toolkit": {"slug": "github", "name": "GitHub"},
                        "version": "v1",
                        "tags": [],
                    }
                ],
                "total_items": 1,
            },
        )

    transport = httpx.MockTransport(handler)
    mock_client = httpx.Client(transport=transport, base_url="https://backend.composio.dev")

    def _factory(connector: dict) -> ComposioAdapter:
        from ax_cli.connectors.providers.composio_adapter import resolve_composio_settings

        settings = resolve_composio_settings(connector)
        return ComposioAdapter(
            api_key=settings["api_key"],
            user_id=settings["user_id"],
            base_url=settings["base_url"],
            client=mock_client,
        )

    from ax_cli.connectors.providers import registry as provider_registry

    monkeypatch.setitem(provider_registry._FACTORIES, "composio", _factory)
    page = list_connector_tools("list_me", query="stars")
    assert page["count"] == 1
