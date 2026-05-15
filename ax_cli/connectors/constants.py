"""Shared constants for the Gateway connector registry and auth layers."""

from __future__ import annotations

import re
from typing import Any

CONNECTORS_SCHEMA_VERSION = 1

# ``auth_ref`` value: secrets live under ``<gateway_dir>/connectors/auth/<id>.env``.
AUTH_REF_MANAGED = "gateway:managed"

# Slug-safe labels for operator UX and future dashboard/API use.
CONNECTOR_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$", re.IGNORECASE)

# Managed auth filenames use the connector UUID/id from the registry row.
CONNECTOR_ID_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,128}$")

MAX_AUTH_REF_LEN = 2048
MAX_CONNECTOR_ID_LEN = 128

FILE_MODE_SECRET = 0o600
FILE_MODE_DIR = 0o700


class _UnsetType:
    __slots__ = ()


# Sentinel for optional patch fields in :func:`registry.update_connector`.
UNSET: Any = _UnsetType()
