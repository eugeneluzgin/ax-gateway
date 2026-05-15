"""Composio provider: direct tool execution via Composio HTTP API."""

from __future__ import annotations

from typing import Any

import httpx

from ..auth import load_connector_auth_env
from .base import ConnectorProviderError, ToolCallResult

PROVIDER_ID = "composio"
DEFAULT_BASE_URL = "https://backend.composio.dev"
DEFAULT_TIMEOUT_SECONDS = 120.0

_API_KEY_ENV_KEYS = ("COMPOSIO_API_KEY", "COMPOSIO_KEY", "COMPOSIO_APIKEY")
_USER_ID_ENV_KEYS = ("COMPOSIO_USER_ID", "COMPOSIO_ENTITY_ID")
_BASE_URL_ENV_KEYS = ("COMPOSIO_BASE_URL",)


def _first_env(env: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        val = str(env.get(key) or "").strip()
        if val:
            return val
    return None


def _connector_config(connector: dict[str, Any]) -> dict[str, Any]:
    cfg = connector.get("config")
    if isinstance(cfg, dict):
        return cfg
    return {}


def resolve_composio_settings(connector: dict[str, Any]) -> dict[str, str]:
    """Resolve API key, user_id, and base URL from auth env + connector config."""
    env = load_connector_auth_env(connector)
    api_key = _first_env(env, _API_KEY_ENV_KEYS)
    if not api_key:
        raise ConnectorProviderError(
            "Composio API key missing. Set COMPOSIO_API_KEY in the connector auth env file."
        )
    cfg = _connector_config(connector)
    user_id = str(cfg.get("user_id") or "").strip() or _first_env(env, _USER_ID_ENV_KEYS)
    if not user_id:
        raise ConnectorProviderError(
            "Composio user_id missing. Set config.user_id on the connector or COMPOSIO_USER_ID in auth env."
        )
    base_url = (
        str(cfg.get("base_url") or "").strip()
        or _first_env(env, _BASE_URL_ENV_KEYS)
        or DEFAULT_BASE_URL
    ).rstrip("/")
    return {"api_key": api_key, "user_id": user_id, "base_url": base_url}


def build_composio_adapter(connector: dict[str, Any]) -> ComposioAdapter:
    settings = resolve_composio_settings(connector)
    return ComposioAdapter(
        api_key=settings["api_key"],
        user_id=settings["user_id"],
        base_url=settings["base_url"],
    )


class ComposioAdapter:
    """Execute Composio tools by slug (``POST /api/v3/tools/execute/{slug}``)."""

    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        api_key: str,
        user_id: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._user_id = user_id.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        if not self._api_key:
            raise ConnectorProviderError("Composio API key is empty")
        if not self._user_id:
            raise ConnectorProviderError("Composio user_id is empty")

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._api_key, "Content-Type": "application/json"}

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            if self._client is not None:
                return self._client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=self._headers(),
                    timeout=self._timeout,
                )
            with httpx.Client(timeout=self._timeout) as client:
                return client.request(method, url, params=params, json=json_body, headers=self._headers())
        except httpx.HTTPError as exc:
            raise ConnectorProviderError(f"Composio request failed: {exc}") from exc

    def get_tools(self, params: dict[str, Any]) -> dict[str, Any]:
        """``GET /api/v3.1/tools`` — Composio catalog with query/toolkit filters."""
        url = f"{self._base_url}/api/v3.1/tools"
        response = self._request("GET", url, params=params)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorProviderError("Composio tools list returned non-JSON response") from exc
        if not isinstance(payload, dict):
            raise ConnectorProviderError("Composio tools list returned unexpected payload")
        if response.status_code >= 400:
            err = payload.get("error") or payload.get("message") or response.reason_phrase
            raise ConnectorProviderError(f"Composio tools list failed: {err}")
        return payload

    def execute_tool(
        self,
        tool_slug: str,
        arguments: dict[str, Any] | None = None,
        *,
        version: str | None = None,
        connected_account_id: str | None = None,
    ) -> ToolCallResult:
        slug = str(tool_slug or "").strip()
        if not slug:
            raise ConnectorProviderError("tool_slug is required")
        body: dict[str, Any] = {
            "user_id": self._user_id,
            "arguments": dict(arguments or {}),
        }
        if version:
            body["version"] = str(version).strip()
        if connected_account_id:
            body["connected_account_id"] = str(connected_account_id).strip()

        url = f"{self._base_url}/api/v3/tools/execute/{slug}"
        response = self._request("POST", url, json_body=body)
        return self._parse_response(slug, response)

    def _parse_response(self, tool_slug: str, response: httpx.Response) -> ToolCallResult:
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": response.text[:500] if response.text else "non-JSON response"}

        if not isinstance(payload, dict):
            payload = {"data": payload}

        if response.status_code >= 400:
            err = payload.get("error") or payload.get("message") or response.reason_phrase
            return ToolCallResult(
                provider=PROVIDER_ID,
                tool_slug=tool_slug,
                successful=False,
                data=payload.get("data"),
                error=str(err),
                log_id=_str_or_none(payload.get("log_id")),
                raw=payload,
            )

        successful = bool(payload.get("successful", True))
        return ToolCallResult(
            provider=PROVIDER_ID,
            tool_slug=tool_slug,
            successful=successful,
            data=payload.get("data"),
            error=_str_or_none(payload.get("error")),
            log_id=_str_or_none(payload.get("log_id")),
            raw=payload,
        )


def _str_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
