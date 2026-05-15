"""Composio tool catalog listing and intent search (Composio-native filtering)."""

from __future__ import annotations

import re
from typing import Any

from ..filtering import ToolFilterPolicy
from .base import ConnectorProviderError, ToolCatalogEntry, ToolSearchResult
from .composio_adapter import ComposioAdapter

_COMPOSIO_SEARCH_TOOL = "COMPOSIO_SEARCH_TOOLS"
_SLUG_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")


def _catalog_entry_from_item(item: dict[str, Any]) -> ToolCatalogEntry | None:
    slug = str(item.get("slug") or "").strip()
    if not slug:
        return None
    toolkit = item.get("toolkit") if isinstance(item.get("toolkit"), dict) else {}
    tags_raw = item.get("tags") if isinstance(item.get("tags"), list) else []
    tags = tuple(str(tag).strip() for tag in tags_raw if str(tag).strip())
    return ToolCatalogEntry(
        slug=slug,
        name=str(item.get("name") or slug).strip(),
        description=str(item.get("description") or item.get("human_description") or "").strip(),
        toolkit_slug=str(toolkit.get("slug") or "").strip() or None,
        toolkit_name=str(toolkit.get("name") or "").strip() or None,
        version=_str_or_none(item.get("version")),
        tags=tags,
    )


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _entries_to_dicts(entries: list[ToolCatalogEntry]) -> list[dict[str, Any]]:
    return [entry.to_dict() for entry in entries]


def list_composio_tools(
    adapter: ComposioAdapter,
    policy: ToolFilterPolicy,
    *,
    query: str | None = None,
    toolkit_slug: str | None = None,
    tool_slugs: list[str] | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """List tools via ``GET /api/v3.1/tools`` and apply Gateway allow/deny policy."""
    effective_limit = limit if limit is not None else policy.default_limit
    effective_limit = max(1, min(int(effective_limit), 200))

    if tool_slugs:
        params: dict[str, Any] = {
            "tool_slugs": ",".join(str(s).strip() for s in tool_slugs if str(s).strip()),
            "limit": effective_limit,
        }
        payload = adapter.get_tools(params)
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        entries = [_catalog_entry_from_item(item) for item in items if isinstance(item, dict)]
        entries = [entry for entry in entries if entry is not None]
        filtered = [entry for entry in entries if _entry_allowed(entry, policy)]
        return {
            "tools": _entries_to_dicts(filtered),
            "count": len(filtered),
            "total_items": payload.get("total_items"),
            "next_cursor": payload.get("next_cursor"),
            "composio_query": params.get("tool_slugs"),
            "policy_applied": policy.has_allowlist or bool(policy.denied_patterns),
        }

    toolkits = [toolkit_slug] if toolkit_slug else list(policy.toolkit_slugs)
    if not toolkits:
        params = {"limit": effective_limit, "query": str(query).strip() if query else None}
        if cursor:
            params["cursor"] = cursor
        payload = adapter.get_tools({k: v for k, v in params.items() if v is not None})
        return _page_from_payload(payload, policy)

    merged: list[ToolCatalogEntry] = []
    seen: set[str] = set()
    last_payload: dict[str, Any] = {}
    per_toolkit = max(1, effective_limit // max(len(toolkits), 1))
    for tk in toolkits:
        params = {
            "toolkit_slug": str(tk).strip().lower(),
            "limit": per_toolkit,
            "query": str(query).strip() if query else None,
        }
        payload = adapter.get_tools({k: v for k, v in params.items() if v is not None})
        last_payload = payload
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            entry = _catalog_entry_from_item(item)
            if entry is None or entry.slug in seen:
                continue
            if not _entry_allowed(entry, policy):
                continue
            seen.add(entry.slug)
            merged.append(entry)
            if len(merged) >= effective_limit:
                break
        if len(merged) >= effective_limit:
            break

    return {
        "tools": _entries_to_dicts(merged[:effective_limit]),
        "count": len(merged[:effective_limit]),
        "total_items": last_payload.get("total_items"),
        "next_cursor": last_payload.get("next_cursor"),
        "toolkit_slugs": list(toolkits),
        "policy_applied": policy.has_allowlist or bool(policy.denied_patterns),
    }


def _page_from_payload(payload: dict[str, Any], policy: ToolFilterPolicy) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    entries = [_catalog_entry_from_item(item) for item in items if isinstance(item, dict)]
    entries = [entry for entry in entries if entry is not None]
    filtered = [entry for entry in entries if _entry_allowed(entry, policy)]
    return {
        "tools": _entries_to_dicts(filtered),
        "count": len(filtered),
        "total_items": payload.get("total_items"),
        "next_cursor": payload.get("next_cursor"),
        "policy_applied": policy.has_allowlist or bool(policy.denied_patterns),
    }


def _entry_allowed(entry: ToolCatalogEntry, policy: ToolFilterPolicy) -> bool:
    from ..filtering import is_tool_allowed

    return is_tool_allowed(entry.slug, policy)


def search_composio_tools_catalog(
    adapter: ComposioAdapter,
    policy: ToolFilterPolicy,
    use_case: str,
    *,
    limit: int | None = None,
) -> ToolSearchResult:
    """Soft search via Composio catalog ``query`` parameter."""
    needle = str(use_case or "").strip()
    if not needle:
        raise ConnectorProviderError("use_case is required for tool search")
    page = list_composio_tools(adapter, policy, query=needle, limit=limit)
    entries = [
        ToolCatalogEntry(
            slug=str(row.get("slug") or ""),
            name=str(row.get("name") or ""),
            description=str(row.get("description") or ""),
            toolkit_slug=row.get("toolkit_slug"),
            toolkit_name=row.get("toolkit_name"),
            version=row.get("version"),
            tags=tuple(row.get("tags") or ()),
        )
        for row in page.get("tools") or []
        if isinstance(row, dict) and row.get("slug")
    ]
    return ToolSearchResult(
        mode="catalog_query",
        use_case=needle,
        tools=tuple(entries),
        successful=True,
        raw=page,
    )


def search_composio_tools_intent(
    adapter: ComposioAdapter,
    policy: ToolFilterPolicy,
    use_case: str,
    *,
    known_fields: str | None = None,
    session_id: str | None = None,
) -> ToolSearchResult:
    """Intent search via Composio ``COMPOSIO_SEARCH_TOOLS`` meta tool."""
    needle = str(use_case or "").strip()
    if not needle:
        raise ConnectorProviderError("use_case is required for tool search")

    query: dict[str, Any] = {"use_case": needle}
    if known_fields:
        query["known_fields"] = str(known_fields).strip()
    arguments: dict[str, Any] = {"queries": [query]}
    if session_id:
        arguments["session"] = {"id": str(session_id).strip()}
    else:
        arguments["session"] = {"generate_id": True}

    result = adapter.execute_tool(_COMPOSIO_SEARCH_TOOL, arguments)
    parsed_tools, parsed_session = _parse_search_tools_response(result.data)
    if not parsed_session and isinstance(result.raw, dict):
        parsed_session = _extract_session_id(result.raw)

    filtered = [tool for tool in parsed_tools if _entry_allowed(tool, policy)]
    return ToolSearchResult(
        mode="composio_search_tools",
        use_case=needle,
        tools=tuple(filtered),
        session_id=parsed_session,
        successful=result.successful,
        error=result.error,
        raw=result.raw if isinstance(result.raw, dict) else {"data": result.data},
    )


def _parse_search_tools_response(data: Any) -> tuple[list[ToolCatalogEntry], str | None]:
    """Best-effort extraction of tool slugs from COMPOSIO_SEARCH_TOOLS output."""
    session_id = _extract_session_id(data) if isinstance(data, dict) else None
    slugs: set[str] = set()
    _collect_slugs(data, slugs)
    tools = [
        ToolCatalogEntry(slug=slug, name=slug, description="")
        for slug in sorted(slugs)
        if _SLUG_RE.match(slug) and slug != _COMPOSIO_SEARCH_TOOL
    ]
    return tools, session_id


def _collect_slugs(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for key in ("tool_slug", "slug", "primary_tool_slugs", "related_tool_slugs"):
            val = node.get(key)
            if isinstance(val, str) and _SLUG_RE.match(val.strip()):
                out.add(val.strip())
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and _SLUG_RE.match(item.strip()):
                        out.add(item.strip())
        for value in node.values():
            _collect_slugs(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_slugs(item, out)
    elif isinstance(node, str) and _SLUG_RE.match(node.strip()) and len(node) > 8:
        out.add(node.strip())


def _extract_session_id(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None
    session = data.get("session")
    if isinstance(session, dict):
        sid = session.get("id") or session.get("session_id")
        if sid:
            return str(sid).strip()
    for key in ("session_id", "sessionId"):
        val = data.get(key)
        if val:
            return str(val).strip()
    return None
