from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture
def sre_setup() -> ModuleType:
    script_path = Path(__file__).parents[3] / "scripts" / "setup_sre_agent.py"
    spec = importlib.util.spec_from_file_location("setup_sre_agent", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repair_skill_renders_deployed_resource_names(sre_setup: ModuleType) -> None:
    name, description, content = sre_setup._load_skill(
        sre_setup.CONFIG_SKILL_PATH,
        {"RG": "rg-demo", "BACKEND_APP": "ca-backend-demo"},
    )

    assert name == "repair-buildingassist-operations-config"
    assert "HTTP 503" in description
    assert "--resource-group rg-demo" in content
    assert "--name ca-backend-demo" in content
    assert "${" not in content


def test_render_config_rejects_unresolved_placeholders(
    sre_setup: ModuleType,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.md"
    config_path.write_text("resource=${MISSING}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Unresolved placeholder"):
        sre_setup._render_config(config_path, {})


def test_handlers_have_disjoint_write_and_github_capabilities(sre_setup: ModuleType) -> None:
    assert "RunAzCliWriteCommands" not in sre_setup.SECURITY_TOOLS
    assert "RunInTerminal" in sre_setup.SECURITY_TOOLS
    assert "RunAzCliWriteCommands" in sre_setup.CONFIG_TOOLS
    assert "RunInTerminal" not in sre_setup.CONFIG_TOOLS
    assert "QueryAppInsightsByAppId" not in sre_setup.CONFIG_TOOLS
    assert "QueryLogAnalyticsByWorkspaceId" in sre_setup.CONFIG_TOOLS
    assert not any("Github" in tool for tool in sre_setup.CONFIG_TOOLS)