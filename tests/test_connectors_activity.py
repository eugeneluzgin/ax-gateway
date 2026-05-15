"""Tests for connector Gateway activity attribution."""

from __future__ import annotations

import json

import httpx
import pytest

from ax_cli.connectors.activity import (
    connector_activity_fields,
    record_connector_tool_finished,
    record_connector_tool_started,
)
from ax_cli.connectors.auth import AUTH_REF_MANAGED, ensure_managed_auth_file
from ax_cli.connectors.providers.base import ConnectorProviderError
from ax_cli.connectors.providers.composio_adapter import ComposioAdapter, resolve_composio_settings
from ax_cli.connectors.providers.dispatch import execute_connector_tool
from ax_cli.connectors.registry import add_connector, load_connectors_registry, save_connectors_registry
from ax_cli.gateway import activity_log_path, load_recent_gateway_activity


def test_connector_activity_fields_redacted():
    row = {
        "id": "cid",
        "name": "my_conn",
        "provider": "composio",
        "config": {"user_id": "u1", "agent_name": "hermes"},
    }
    fields = connector_activity_fields(row)
    assert fields["connector_name"] == "my_conn"
    assert fields["linked_agent_name"] == "hermes"
    assert "user_id" not in fields


def test_record_connector_tool_started_writes_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    row = {"id": "1", "name": "c", "provider": "composio"}
    rec = record_connector_tool_started(row, "GITHUB_LIST_STARGAZERS", tool_call_id="call-1")
    assert rec["event"] == "connector_tool_started"
    assert rec["phase"] == "tool"
    assert rec["tool_call_id"] == "call-1"
    assert rec["connector_name"] == "c"
    path = activity_log_path()
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    payload = json.loads(lines[-1])
    assert payload["event"] == "connector_tool_started"


def test_execute_connector_tool_records_start_and_finish(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = load_connectors_registry()
    rec = add_connector(
        reg,
        name="act_test",
        provider="composio",
        auth_ref=AUTH_REF_MANAGED,
        config={"user_id": "u"},
    )
    save_connectors_registry(reg)
    ensure_managed_auth_file(str(rec["id"]))
    (tmp_path / "connectors" / "auth" / f"{rec['id']}.env").write_text("COMPOSIO_API_KEY=k\n", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"successful": True, "data": {"n": 1}, "error": None, "log_id": "log_x"})

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

    result = execute_connector_tool("act_test", "SOME_TOOL", {"a": 1})
    assert result.successful is True

    events = [item["event"] for item in load_recent_gateway_activity(limit=10)]
    assert "connector_tool_started" in events
    assert "connector_tool_completed" in events


def test_execute_connector_tool_records_failure_on_provider_error(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = load_connectors_registry()
    add_connector(reg, name="bad", provider="composio", auth_ref=AUTH_REF_MANAGED, config={})
    save_connectors_registry(reg)
    with pytest.raises(ConnectorProviderError):
        execute_connector_tool("bad", "TOOL", {})
    events = [item["event"] for item in load_recent_gateway_activity(limit=10)]
    assert "connector_tool_started" in events
    assert "connector_tool_failed" in events


def test_record_connector_tool_finished_failed_phase(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    row = {"id": "1", "name": "c", "provider": "composio"}
    rec = record_connector_tool_finished(
        row,
        "TOOL",
        tool_call_id="call-2",
        successful=False,
        error="rate limited",
    )
    assert rec["event"] == "connector_tool_failed"
    assert rec["phase"] == "result"
    assert rec["successful"] is False
