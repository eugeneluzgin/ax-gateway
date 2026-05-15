"""Gateway tool filter policy for connector tool catalogs and execution."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any

from .errors import ConnectorProviderError

DEFAULT_TOOLS_LIMIT = 50
MAX_TOOLS_LIMIT = 200


@dataclass(frozen=True, slots=True)
class ToolFilterPolicy:
    """Operator-defined constraints applied after Composio returns candidates."""

    allowed_patterns: tuple[str, ...] = ()
    denied_patterns: tuple[str, ...] = ()
    toolkit_slugs: tuple[str, ...] = ()
    default_limit: int = DEFAULT_TOOLS_LIMIT

    @property
    def has_allowlist(self) -> bool:
        return bool(self.allowed_patterns)


def _normalize_patterns(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        return tuple(parts)
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _normalize_toolkits(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        slug = value.strip().lower()
        return (slug,) if slug else ()
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            slug = str(item).strip().lower()
            if slug and slug not in out:
                out.append(slug)
        return tuple(out)
    return ()


def resolve_tool_filter_policy(connector: dict[str, Any]) -> ToolFilterPolicy:
    """Build filter policy from ``connector["config"]`` (non-secret fields only)."""
    cfg = connector.get("config")
    if not isinstance(cfg, dict):
        cfg = {}
    limit_raw = cfg.get("tools_limit") or cfg.get("tool_limit")
    try:
        limit = int(limit_raw) if limit_raw is not None else DEFAULT_TOOLS_LIMIT
    except (TypeError, ValueError):
        limit = DEFAULT_TOOLS_LIMIT
    limit = max(1, min(limit, MAX_TOOLS_LIMIT))
    return ToolFilterPolicy(
        allowed_patterns=_normalize_patterns(cfg.get("allowed_tools") or cfg.get("allow_tools")),
        denied_patterns=_normalize_patterns(cfg.get("denied_tools") or cfg.get("deny_tools")),
        toolkit_slugs=_normalize_toolkits(cfg.get("toolkits") or cfg.get("toolkit_slug") or cfg.get("toolkit")),
        default_limit=limit,
    )


def _matches_any(slug: str, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return False
    upper = slug.upper()
    for pattern in patterns:
        pat = str(pattern).strip().upper()
        if not pat:
            continue
        if fnmatch.fnmatchcase(upper, pat):
            return True
    return False


def is_tool_allowed(tool_slug: str, policy: ToolFilterPolicy) -> bool:
    """Return whether ``tool_slug`` may be executed under ``policy``."""
    slug = str(tool_slug or "").strip()
    if not slug:
        return False
    if policy.denied_patterns and _matches_any(slug, policy.denied_patterns):
        return False
    if policy.has_allowlist and not _matches_any(slug, policy.allowed_patterns):
        return False
    return True


def assert_tool_allowed(tool_slug: str, policy: ToolFilterPolicy, *, connector_name: str | None = None) -> None:
    if is_tool_allowed(tool_slug, policy):
        return
    label = f"connector {connector_name!r}" if connector_name else "connector"
    if policy.has_allowlist:
        raise ConnectorProviderError(
            f"tool {tool_slug!r} is not allowed by {label} allowed_tools policy "
            f"(patterns: {', '.join(policy.allowed_patterns)})"
        )
    raise ConnectorProviderError(f"tool {tool_slug!r} is denied by {label} denied_tools policy")


def apply_policy_to_tools(tools: list[dict[str, Any]], policy: ToolFilterPolicy) -> list[dict[str, Any]]:
    """Filter catalog rows by allow/deny patterns."""
    return [tool for tool in tools if is_tool_allowed(str(tool.get("slug") or ""), policy)]


@dataclass(frozen=True, slots=True)
class ToolCatalogPage:
    """Paginated tool catalog slice returned to operators."""

    tools: list[dict[str, Any]] = field(default_factory=list)
    total_items: int | None = None
    next_cursor: str | None = None
    provider: str = ""
    connector_name: str = ""
    policy_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "connector_name": self.connector_name,
            "tools": self.tools,
            "count": len(self.tools),
            "total_items": self.total_items,
            "next_cursor": self.next_cursor,
            "policy_applied": self.policy_applied,
        }
