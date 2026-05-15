"""Smoke tests for ax_cli.connectors package layout (phase 3)."""

from __future__ import annotations

import ax_cli.connectors as connectors
import ax_cli.connectors.auth as auth_mod
import ax_cli.connectors.constants as constants_mod
import ax_cli.connectors.envfile as envfile_mod
import ax_cli.connectors.paths as paths_mod
import ax_cli.connectors.registry as registry_mod
import ax_cli.connectors.storage as storage_mod
import ax_cli.connectors.validation as validation_mod


def test_public_api_matches_submodules():
    import ax_cli.connectors.providers as providers_mod

    assert connectors.AUTH_REF_MANAGED is constants_mod.AUTH_REF_MANAGED
    assert connectors.CONNECTORS_SCHEMA_VERSION is constants_mod.CONNECTORS_SCHEMA_VERSION
    assert connectors.connectors_registry_path is paths_mod.connectors_registry_path
    assert connectors.connectors_auth_env_base is paths_mod.connectors_auth_env_base
    assert connectors.load_connectors_registry is registry_mod.load_connectors_registry
    assert connectors.parse_dotenv is envfile_mod.parse_dotenv
    assert connectors.uses_managed_auth is auth_mod.uses_managed_auth
    assert connectors.execute_connector_tool is providers_mod.execute_connector_tool
    assert "composio" in connectors.SUPPORTED_PROVIDERS


def test_package_exports_documented_symbols():
    expected = {
        "AUTH_REF_MANAGED",
        "CONNECTORS_SCHEMA_VERSION",
        "ConnectorRecord",
        "ConnectorRegistry",
        "add_connector",
        "connectors_auth_env_base",
        "connectors_registry_path",
        "load_connectors_registry",
        "save_connectors_registry",
    }
    assert expected.issubset(set(connectors.__all__))


def test_constants_single_source_of_truth():
    assert constants_mod.AUTH_REF_MANAGED == "gateway:managed"
    assert constants_mod.CONNECTORS_SCHEMA_VERSION == 1


def test_validation_delegates_to_constants(tmp_path, monkeypatch):
    monkeypatch.setenv("AX_GATEWAY_DIR", str(tmp_path))
    reg = validation_mod.default_connectors_registry()
    assert reg["version"] == constants_mod.CONNECTORS_SCHEMA_VERSION
    assert storage_mod.utc_now_iso().endswith("+00:00") or "T" in storage_mod.utc_now_iso()
