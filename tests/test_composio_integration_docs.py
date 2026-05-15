"""Phase 8: composio integration docs and operator skill are present and wired."""

from __future__ import annotations

from pathlib import Path

from ax_cli.gateway_runtime_types import agent_template_definition

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "composio-integration.md"
SKILL_PATH = REPO_ROOT / "skills" / "gateway-composio-connectors" / "SKILL.md"


def test_composio_integration_doc_exists() -> None:
    assert DOC_PATH.is_file(), f"missing operator doc at {DOC_PATH}"
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "ax gateway connectors" in text
    assert "gateway:managed" in text or "managed-auth" in text
    assert "allowed_tools" in text


def test_gateway_composio_skill_exists() -> None:
    assert SKILL_PATH.is_file(), f"missing skill at {SKILL_PATH}"
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "name: gateway-composio-connectors" in text
    assert "tools search" in text
    assert "Never" in text or "never" in text


def test_langgraph_composio_template_points_at_composio_skill() -> None:
    template = agent_template_definition("langgraph_composio")
    assert template["setup_skill"] == "gateway-composio-connectors"
    skill_path = Path(str(template["setup_skill_path"]))
    assert skill_path == SKILL_PATH
