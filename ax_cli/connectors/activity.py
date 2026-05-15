"""Gateway activity attribution for outbound connector tool calls."""

from __future__ import annotations

import uuid
from typing import Any

from ax_cli.gateway import find_agent_entry, load_gateway_registry, record_gateway_activity

from .constants import CONNECTOR_ACTIVITY_EVENTS

_ACTIVITY_MESSAGE_LIMIT = 240
_TOOL_NAME_LIMIT = 120


def connector_activity_fields(connector: dict[str, Any]) -> dict[str, Any]:
    """Build redacted activity payload fields for a connector row."""
    name = str(connector.get("name") or "").strip()
    cid = str(connector.get("id") or "").strip()
    provider = str(connector.get("provider") or "").strip()
    fields: dict[str, Any] = {}
    if name:
        fields["connector_name"] = name
    if cid:
        fields["connector_id"] = cid
    if provider:
        fields["provider"] = provider
    cfg = connector.get("config")
    if isinstance(cfg, dict):
        agent_name = str(cfg.get("agent_name") or cfg.get("linked_agent") or "").strip()
        if agent_name:
            fields["linked_agent_name"] = agent_name
    return fields


def _linked_agent_entry(connector: dict[str, Any]) -> dict[str, Any] | None:
    cfg = connector.get("config")
    if not isinstance(cfg, dict):
        return None
    agent_name = str(cfg.get("agent_name") or cfg.get("linked_agent") or "").strip()
    if not agent_name:
        return None
    registry = load_gateway_registry()
    return find_agent_entry(registry, agent_name)


def _tool_display_name(connector: dict[str, Any], tool_slug: str) -> str:
    provider = str(connector.get("provider") or "connector").strip()
    slug = str(tool_slug or "").strip() or "tool"
    label = f"{provider}/{slug}"
    return label[:_TOOL_NAME_LIMIT]


def _activity_message(text: str) -> str:
    return str(text or "").strip()[:_ACTIVITY_MESSAGE_LIMIT]


def record_connector_tool_started(
    connector: dict[str, Any],
    tool_slug: str,
    *,
    tool_call_id: str | None = None,
) -> dict[str, Any]:
    """Record that a connector tool invocation has started."""
    call_id = str(tool_call_id or uuid.uuid4())
    name = str(connector.get("name") or "connector").strip()
    message = _activity_message(f"Connector {name}: calling {tool_slug}")
    return record_gateway_activity(
        CONNECTOR_ACTIVITY_EVENTS["started"],
        entry=_linked_agent_entry(connector),
        tool_name=_tool_display_name(connector, tool_slug),
        tool_call_id=call_id,
        activity_message=message,
        **connector_activity_fields(connector),
    )


def record_connector_tool_finished(
    connector: dict[str, Any],
    tool_slug: str,
    *,
    tool_call_id: str | None,
    successful: bool,
    error: str | None = None,
    log_id: str | None = None,
) -> dict[str, Any]:
    """Record terminal outcome for a connector tool invocation."""
    name = str(connector.get("name") or "connector").strip()
    if successful:
        event = CONNECTOR_ACTIVITY_EVENTS["completed"]
        message = _activity_message(f"Connector {name}: {tool_slug} succeeded")
    else:
        event = CONNECTOR_ACTIVITY_EVENTS["failed"]
        detail = _activity_message(error or "tool execution failed")
        message = _activity_message(f"Connector {name}: {tool_slug} failed — {detail}")

    fields: dict[str, Any] = {
        "tool_name": _tool_display_name(connector, tool_slug),
        "activity_message": message,
        "successful": successful,
        **connector_activity_fields(connector),
    }
    if tool_call_id:
        fields["tool_call_id"] = tool_call_id
    if log_id:
        fields["log_id"] = log_id
    if not successful and error:
        fields["error"] = _activity_message(error)

    return record_gateway_activity(
        event,
        entry=_linked_agent_entry(connector),
        **fields,
    )
