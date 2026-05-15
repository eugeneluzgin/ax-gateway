"""Minimal dotenv parsing for connector auth files (no shell expansion)."""

from __future__ import annotations

import re


def parse_dotenv(content: str) -> dict[str, str]:
    """Parse KEY=VALUE lines. Values are sensitive — do not log."""
    result: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        k = key.strip()
        if not k or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", k):
            continue
        v = value.strip()
        if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
            v = v[1:-1]
        result[k] = v
    return result
