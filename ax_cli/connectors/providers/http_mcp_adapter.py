"""HTTP MCP provider: JSON-RPC tools/list and tools/call against a remote MCP endpoint."""

from __future__ import annotations

from typing import Any

import httpx

from ..auth import load_connector_auth_env
from .base import ConnectorProviderError, ToolCallResult

PROVIDER_ID = "http_mcp"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TIMEOUT_SECONDS = 120.0

_AUTH_BEARER_KEYS = ("MCP_BEARER_TOKEN", "MCP_TOKEN", "MCP_ACCESS_TOKEN")
_AUTH_AUTHORIZATION_KEYS = ("MCP_AUTHORIZATION", "AUTHORIZATION")
_AUTH_API_KEY_KEYS = ("MCP_API_KEY", "API_KEY")


def _connector_config(connector: dict[str, Any]) -> dict[str, Any]:
    cfg = connector.get("config")
    if isinstance(cfg, dict):
        return cfg
    return {}


def _first_env(env: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        val = str(env.get(key) or "").strip()
        if val:
            return val
    return None


def resolve_http_mcp_settings(connector: dict[str, Any]) -> dict[str, str]:
    """Resolve base URL and auth headers from connector config + auth env."""
    cfg = _connector_config(connector)
    base_url = str(cfg.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        raise ConnectorProviderError(
            "http_mcp base_url missing. Set config.base_url to the MCP HTTP endpoint URL."
        )
    env = load_connector_auth_env(connector)
    headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    bearer = _first_env(env, _AUTH_BEARER_KEYS)
    if bearer:
        headers["Authorization"] = bearer if bearer.lower().startswith("bearer ") else f"Bearer {bearer}"
    else:
        authorization = _first_env(env, _AUTH_AUTHORIZATION_KEYS)
        if authorization:
            headers["Authorization"] = authorization
    api_key = _first_env(env, _AUTH_API_KEY_KEYS)
    if api_key:
        header_name = str(cfg.get("api_key_header") or "X-API-Key").strip() or "X-API-Key"
        headers[header_name] = api_key
    return {
        "base_url": base_url,
        "protocol_version": str(cfg.get("protocol_version") or DEFAULT_PROTOCOL_VERSION).strip()
        or DEFAULT_PROTOCOL_VERSION,
        "skip_initialize": bool(cfg.get("skip_initialize")),
        "headers": headers,
    }


def build_http_mcp_adapter(connector: dict[str, Any]) -> HttpMcpAdapter:
    settings = resolve_http_mcp_settings(connector)
    return HttpMcpAdapter(
        base_url=settings["base_url"],
        headers=dict(settings["headers"]),
        protocol_version=settings["protocol_version"],
        skip_initialize=bool(settings["skip_initialize"]),
    )


class HttpMcpAdapter:
    """Minimal MCP JSON-RPC client for tools/list and tools/call."""

    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str],
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
        skip_initialize: bool = False,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = dict(headers)
        self._protocol_version = protocol_version
        self._skip_initialize = skip_initialize
        self._timeout = timeout_seconds
        self._client = client
        self._initialized = skip_initialize
        self._next_id = 1

    def _next_request_id(self) -> int:
        rid = self._next_id
        self._next_id += 1
        return rid

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = self._client.post(
                    self._base_url,
                    json=payload,
                    headers=self._headers,
                    timeout=self._timeout,
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(self._base_url, json=payload, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ConnectorProviderError(f"MCP HTTP request failed: {exc}") from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise ConnectorProviderError("MCP endpoint returned non-JSON response") from exc
        if not isinstance(body, dict):
            raise ConnectorProviderError("MCP endpoint returned unexpected JSON payload")
        if "error" in body and body["error"] is not None:
            err = body["error"]
            if isinstance(err, dict):
                message = str(err.get("message") or err.get("code") or err)
            else:
                message = str(err)
            raise ConnectorProviderError(f"MCP error: {message}")
        if response.status_code >= 400:
            raise ConnectorProviderError(f"MCP HTTP {response.status_code}: {body}")
        result = body.get("result")
        if not isinstance(result, dict):
            return {"result": result}
        return result

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        init_id = self._next_request_id()
        self._post(
            {
                "jsonrpc": "2.0",
                "id": init_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": self._protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "ax-gateway-connector", "version": "1.0"},
                },
            }
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        self._initialized = True

    def list_tools_raw(self) -> list[dict[str, Any]]:
        self._ensure_initialized()
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "tools/list",
                "params": {},
            }
        )
        tools = result.get("tools")
        if not isinstance(tools, list):
            return []
        return [tool for tool in tools if isinstance(tool, dict)]

    def execute_tool(
        self,
        tool_slug: str,
        arguments: dict[str, Any] | None = None,
        *,
        version: str | None = None,
        connected_account_id: str | None = None,
    ) -> ToolCallResult:
        _ = version, connected_account_id
        name = str(tool_slug or "").strip()
        if not name:
            raise ConnectorProviderError("tool_slug is required")
        self._ensure_initialized()
        try:
            result = self._post(
                {
                    "jsonrpc": "2.0",
                    "id": self._next_request_id(),
                    "method": "tools/call",
                    "params": {"name": name, "arguments": dict(arguments or {})},
                }
            )
        except ConnectorProviderError as exc:
            return ToolCallResult(
                provider=PROVIDER_ID,
                tool_slug=name,
                successful=False,
                error=str(exc),
                log_id=None,
                raw={},
            )
        is_error = bool(result.get("isError"))
        content = result.get("content")
        return ToolCallResult(
            provider=PROVIDER_ID,
            tool_slug=name,
            successful=not is_error,
            data=content,
            error="tool returned isError=true" if is_error else None,
            log_id=None,
            raw=result if isinstance(result, dict) else {"result": result},
        )
