"""Gateway outbound connector registry (tool providers, MCP backends, etc.)."""

from .registry import (
    CONNECTORS_SCHEMA_VERSION,
    add_connector,
    connectors_registry_path,
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

__all__ = [
    "CONNECTORS_SCHEMA_VERSION",
    "add_connector",
    "connectors_registry_path",
    "default_connectors_registry",
    "find_connector",
    "list_connectors",
    "load_connectors_registry",
    "normalize_connector_record",
    "remove_connector",
    "save_connectors_registry",
    "update_connector",
    "validate_connector_record",
]
