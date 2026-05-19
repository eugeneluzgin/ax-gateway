"""Tool catalog helpers for HTTP MCP connectors."""

from __future__ import annotations

from typing import Any

from ..filtering import ToolFilterPolicy, is_tool_allowed
from .base import ToolCatalogEntry, ToolSearchResult
from .http_mcp_adapter import HttpMcpAdapter


def _entry_from_mcp_tool(tool: dict[str, Any]) -> ToolCatalogEntry | None:
    name = str(tool.get("name") or "").strip()
    if not name:
        return None
    description = str(tool.get("description") or "").strip()
    return ToolCatalogEntry(
        slug=name,
        name=name,
        description=description,
        toolkit_slug=None,
        toolkit_name=None,
        version=None,
        tags=(),
    )


def _entries_to_dicts(entries: list[ToolCatalogEntry]) -> list[dict[str, Any]]:
    return [entry.to_dict() for entry in entries]


def list_http_mcp_tools(
    adapter: HttpMcpAdapter,
    policy: ToolFilterPolicy,
    *,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """List tools via MCP ``tools/list`` and apply Gateway allow/deny policy."""
    effective_limit = limit if limit is not None else policy.default_limit
    effective_limit = max(1, min(int(effective_limit), 200))
    raw_tools = adapter.list_tools_raw()
    entries: list[ToolCatalogEntry] = []
    for item in raw_tools:
        entry = _entry_from_mcp_tool(item)
        if entry is None:
            continue
        if query:
            needle = str(query).strip().lower()
            hay = f"{entry.name} {entry.description} {entry.slug}".lower()
            if needle not in hay:
                continue
        if is_tool_allowed(entry.slug, policy):
            entries.append(entry)
        if len(entries) >= effective_limit:
            break
    return {
        "tools": _entries_to_dicts(entries),
        "count": len(entries),
        "total_items": len(raw_tools),
        "next_cursor": None,
        "policy_applied": policy.has_allowlist or bool(policy.denied_patterns),
    }


def search_http_mcp_tools_catalog(
    adapter: HttpMcpAdapter,
    policy: ToolFilterPolicy,
    use_case: str,
    *,
    limit: int | None = None,
) -> ToolSearchResult:
    """Text search over MCP tools/list results (no intent API)."""
    page = list_http_mcp_tools(adapter, policy, query=use_case, limit=limit)
    tools_raw = page.get("tools") if isinstance(page.get("tools"), list) else []
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
        for row in tools_raw
        if isinstance(row, dict) and row.get("slug")
    ]
    return ToolSearchResult(
        mode="catalog",
        use_case=use_case,
        tools=tuple(entries),
        session_id=None,
        successful=True,
        error=None,
        raw={"page": page},
    )
