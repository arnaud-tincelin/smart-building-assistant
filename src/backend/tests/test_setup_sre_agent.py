from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture()
def setup(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "setup_sre_agent", Path(__file__).resolve().parents[3] / "scripts/setup_sre_agent.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in {
        "AZURE_SUBSCRIPTION_ID": "sub", "AZURE_RESOURCE_GROUP": "rg",
        "SRE_AGENT_NAME": "sre-demo", "SRE_CONFIG_REPAIR_ENABLED": "true",
        "SERVICE_BACKEND_RESOURCE_ID": (
            "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.App/containerApps/ca-backend-demo"
        ),
        "SERVICE_BACKEND_URL": "https://ca-backend-demo.example.azurecontainerapps.io",
    }.items():
        monkeypatch.setenv(name, value)
    return module


def test_managed_instructions_preserve_existing_and_are_idempotent(setup: ModuleType) -> None:
    first = setup._merge_chat_instructions("Keep operator instructions.", "old")
    updated = setup._merge_chat_instructions(first + "\nKeep the suffix.", "new")
    assert updated.startswith("Keep operator instructions.")
    assert updated.endswith("Keep the suffix.")
    assert setup._merge_chat_instructions(updated, "new") == updated
    assert "old" not in updated


@pytest.mark.parametrize("markers", ["start", "end", "duplicate", "reversed"])
def test_malformed_markers_cannot_overwrite_instructions(setup: ModuleType, markers: str) -> None:
    text = {
        "start": setup.CHAT_START,
        "end": setup.CHAT_END,
        "duplicate": setup.CHAT_START * 2 + setup.CHAT_END,
        "reversed": setup.CHAT_END + setup.CHAT_START,
    }[markers]
    with pytest.raises(RuntimeError):
        setup._merge_chat_instructions(text, "replacement")


@pytest.mark.parametrize("enabled", [True, False])
def test_chat_setup_checks_tools_preserves_instructions_and_reads_back(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    monkeypatch.setenv("SRE_CONFIG_REPAIR_ENABLED", str(enabled).lower())
    saved = {"instructions": "Existing guidance."}
    calls = []

    def request(method: str, url: str, _token: str, body: dict | None = None) -> dict:
        calls.append((method, url, body))
        if url.endswith("/tools"):
            tools = ["RunAzCliReadCommands", "QueryLogAnalyticsByWorkspaceId"]
            if enabled:
                tools.append("RunAzCliWriteCommands")
            return {"data": [{"name": name} for name in tools]}
        if method == "PUT":
            saved.update(body)
        return saved.copy()

    monkeypatch.setattr(setup, "_request_json", request)
    setup._ensure_chat_playbook("https://sre.example", "token")
    assert [method for method, *_ in calls] == ["GET", "GET", "PUT", "GET"]
    assert saved["instructions"].startswith("Existing guidance.")
    assert "{{" not in saved["instructions"]
    assert f"Repair enabled for this installation: {str(enabled).lower()}" in saved["instructions"]
    assert "explicitly approve" in saved["instructions"]
    assert "security audit defect" in saved["instructions"]


def test_missing_write_tool_prevents_chat_configuration(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def request(method: str, *_args: object) -> dict:
        calls.append(method)
        return {"data": [{"name": name} for name in (
            "RunAzCliReadCommands", "QueryLogAnalyticsByWorkspaceId",
        )]}

    monkeypatch.setattr(setup, "_request_json", request)
    with pytest.raises(RuntimeError, match="RunAzCliWriteCommands"):
        setup._ensure_chat_playbook("https://sre.example", "token")
    assert calls == ["GET"]


def test_mismatched_target_cannot_write(setup: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICE_BACKEND_URL", "https://other.example")
    monkeypatch.setattr(setup, "_request_json", lambda *_: pytest.fail("Unexpected network call"))
    with pytest.raises(RuntimeError, match="matching backend"):
        setup._ensure_chat_playbook("https://sre.example", "token")


def test_chat_only_does_not_reconfigure_alerts_or_repository(
    setup: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(setup.sys, "argv", ["setup_sre_agent.py", "--chat-config-only"])
    monkeypatch.setattr(setup, "_azd_token", lambda _: "token")
    monkeypatch.setattr(setup, "_request_json", lambda *_: {
        "properties": {"agentEndpoint": "https://sre.example"},
    })
    calls = []
    for name in (
        "_ensure_chat_playbook", "_ensure_handler", "_ensure_response_plan", "_ensure_repository"
    ):
        monkeypatch.setattr(setup, name, lambda *_, name=name: calls.append(name))
    assert setup.main() == 0
    assert calls == ["_ensure_chat_playbook", "_ensure_handler"]


def test_security_handler_never_repairs_configuration(setup: ModuleType) -> None:
    assert "configuration_error" in setup.HANDLER_INSTRUCTIONS
    assert "Do not\nrepair those failures" in setup.HANDLER_INSTRUCTIONS
