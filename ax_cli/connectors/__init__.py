"""Gateway outbound connectors: registry, auth storage, and provider adapters.

Package layout:

- :mod:`constants` — schema version, ``AUTH_REF_MANAGED``, validation limits
- :mod:`paths` — ``connectors.json`` and managed auth directory paths
- :mod:`storage` — atomic JSON read/write under the Gateway dir
- :mod:`validation` — row validate/normalize and registry coercion
- :mod:`registry` — load/save and CRUD
- :mod:`auth` — managed ``.env`` files and external auth paths
- :mod:`envfile` — dotenv parsing for auth files
- :mod:`types` — ``TypedDict`` shapes for registry rows
- :mod:`activity` — Gateway activity.jsonl attribution for connector tools
- :mod:`providers` — provider adapters (Composio tool execution)

Import from this package (``from ax_cli.connectors import …``) rather than
submodules unless you are extending the connector layer.
"""

from .activity import (
    connector_activity_fields,
    record_connector_tool_finished,
    record_connector_tool_started,
)
from .auth import (
    AUTH_REF_MANAGED,
    connectors_auth_env_base,
    delete_managed_auth_file,
    ensure_connectors_auth_env_dir,
    ensure_managed_auth_file,
    load_connector_auth_env,
    parse_dotenv,
    public_auth_status,
    release_managed_auth_if_unused,
    resolve_auth_env_path,
    uses_managed_auth,
    write_managed_auth_from_file,
)
from .constants import CONNECTORS_SCHEMA_VERSION
from .paths import connectors_registry_path
from .providers import (
    SUPPORTED_PROVIDERS,
    ConnectorProviderError,
    ToolCallResult,
    adapter_for_connector,
    execute_connector_tool,
)
from .registry import (
    add_connector,
    default_connectors_registry,
    find_connector,
    list_connectors,
    load_connectors_registry,
    normalize_connector_record,
    remove_connector,
    save_connectors_registry,
    update_connector,
    validate_connector_record,
)
from .types import ConnectorRecord, ConnectorRegistry

__all__ = [
    "AUTH_REF_MANAGED",
    "CONNECTORS_SCHEMA_VERSION",
    "ConnectorProviderError",
    "ConnectorRecord",
    "ConnectorRegistry",
    "SUPPORTED_PROVIDERS",
    "ToolCallResult",
    "adapter_for_connector",
    "add_connector",
    "connector_activity_fields",
    "connectors_auth_env_base",
    "connectors_registry_path",
    "default_connectors_registry",
    "delete_managed_auth_file",
    "ensure_connectors_auth_env_dir",
    "ensure_managed_auth_file",
    "execute_connector_tool",
    "find_connector",
    "record_connector_tool_finished",
    "record_connector_tool_started",
    "list_connectors",
    "load_connector_auth_env",
    "load_connectors_registry",
    "normalize_connector_record",
    "parse_dotenv",
    "public_auth_status",
    "release_managed_auth_if_unused",
    "remove_connector",
    "resolve_auth_env_path",
    "save_connectors_registry",
    "update_connector",
    "uses_managed_auth",
    "validate_connector_record",
    "write_managed_auth_from_file",
]
