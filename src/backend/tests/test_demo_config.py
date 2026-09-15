from __future__ import annotations

import importlib.util
import io
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

SPEC = importlib.util.spec_from_file_location(
    "demo_config", Path(__file__).resolve().parents[3] / "scripts/demo_config.py"
)
assert SPEC and SPEC.loader
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


def test_cli_resolves_windows_command_path(monkeypatch: pytest.MonkeyPatch) -> None:
    executable = r"C:\Program Files\Azure\az.cmd"
    resolve = Mock(return_value=executable)
    run = Mock(return_value=demo.subprocess.CompletedProcess([], 0, " result\n", ""))
    monkeypatch.setattr(demo.shutil, "which", resolve)
    monkeypatch.setattr(demo.subprocess, "run", run)
    assert demo.run_cli("az", "containerapp", "show") == "result"
    resolve.assert_called_once_with("az")
    run.assert_called_once_with(
        (executable, "containerapp", "show"), capture_output=True, text=True, check=False
    )


def test_missing_cli_is_reported_before_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(demo.shutil, "which", lambda _: None)
    run = Mock()
    monkeypatch.setattr(demo.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="Required CLI not found on PATH: az"):
        demo.run_cli("az", "containerapp", "show")
    run.assert_not_called()


def state(source: str = "simulator") -> dict:
    return {
        "id": "backend-id", "state": "Succeeded", "latest": "rev", "ready": "rev",
        "mode": "Single", "ingress": {"fqdn": "ca-backend-demo.example.azurecontainerapps.io"},
        "template": {"containers": [{"image": "unchanged-image", "env": [
            {"name": demo.SETTING, "value": source},
            {"name": "GATEWAY_KEY", "secretRef": "keep-this-reference"},
        ]}]},
    }


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch) -> dict:
    context = {"before": state(), "commands": [], "probes": []}
    monkeypatch.setattr(demo, "load_target", lambda _: (
        ["--subscription", "sub", "--resource-group", "rg", "--name", "ca-backend-demo"],
        "https://ca-backend-demo.example.azurecontainerapps.io",
    ))
    monkeypatch.setattr(demo, "read_state", lambda *_: deepcopy(
        context.get("after", context["before"]) if context["commands"] else context["before"]
    ))
    monkeypatch.setattr(demo, "run_cli", lambda *args: context["commands"].append(args))
    monkeypatch.setattr(demo, "probe", lambda url, code: context["probes"].append(code))
    return context


def test_dry_run_cannot_write(harness: dict) -> None:
    assert demo.execute("break", "demo") == 0
    assert harness["commands"] == []
    assert harness["probes"] == []


@pytest.mark.parametrize(("action", "before", "after", "probes"), [
    ("break", "simulator", "bms-prod", [200, 503]),
    ("fix", "bms-prod", "simulator", [200]),
])
def test_only_the_demo_setting_is_written(
    harness: dict, action: str, before: str, after: str, probes: list[int]
) -> None:
    harness["before"] = state(before)
    harness["after"] = state(after)
    assert demo.execute(action, "demo", apply=True) == 0
    assert harness["probes"] == probes
    assert harness["commands"] == [(
        "az", "containerapp", "update", "--subscription", "sub", "--resource-group", "rg",
        "--name", "ca-backend-demo", "--set-env-vars", f"{demo.SETTING}={after}",
        "--output", "none",
    )]


@pytest.mark.parametrize("problem", ["unexpected-source", "secret", "multiple", "pending"])
def test_unsafe_break_is_refused(harness: dict, problem: str) -> None:
    if problem == "unexpected-source":
        harness["before"] = state("something-else")
    elif problem == "secret":
        harness["before"]["template"]["containers"][0]["env"][0]["secretRef"] = "secret"
    elif problem == "multiple":
        harness["before"]["mode"] = "Multiple"
    else:
        harness["before"]["ready"] = "old"
    with pytest.raises(RuntimeError):
        demo.execute("break", "demo", apply=True)
    assert harness["commands"] == []


def test_old_image_preflight_cannot_mutate(harness: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    def unsupported(*_args: object) -> None:
        raise RuntimeError("Deploy the configuration-demo backend")
    monkeypatch.setattr(demo, "probe", unsupported)
    with pytest.raises(RuntimeError, match="Deploy"):
        demo.execute("break", "demo", apply=True)
    assert harness["commands"] == []


def test_detects_concurrent_image_change(harness: dict) -> None:
    harness["after"] = state("bms-prod")
    harness["after"]["template"]["containers"][0]["image"] = "changed"
    with pytest.raises(RuntimeError, match="concurrently"):
        demo.execute("break", "demo", apply=True)
    assert len(harness["commands"]) == 1


def test_pending_rollout_is_not_reported_as_verified(harness: dict) -> None:
    harness["after"] = state("bms-prod")
    harness["after"]["ready"] = "old"
    assert demo.execute("break", "demo", apply=True) == 2
    assert harness["probes"] == [200]


@pytest.mark.parametrize(("status", "headers", "body", "valid"), [
    (200, {"X-Operations-Config": "v1"}, {"simulation": True, "buildings": ["HQ"]}, True),
    (200, {}, {"simulation": True, "buildings": ["HQ"]}, False),
    (200, {"X-Operations-Config": "v1"}, {"simulation": True, "buildings": []}, False),
    (503, {"X-Operations-Config": "v1", "X-Error-Code": "configuration_error"}, {}, True),
    (503, {"X-Operations-Config": "v1"}, {}, False),
])
def test_probe_validates_the_actual_response_contract(
    monkeypatch: pytest.MonkeyPatch, status: int, headers: dict, body: dict, valid: bool
) -> None:
    response = demo.HTTPError(
        "https://backend.example", status, "test response", headers,
        io.BytesIO(json.dumps(body).encode()),
    )

    def open_url(url: str, timeout: int) -> object:
        assert url == "https://backend.example/operations/buildings"
        assert timeout == 30
        if status == 503:
            raise response
        return response

    monkeypatch.setattr(demo, "urlopen", open_url)
    if valid:
        demo.probe("https://backend.example", status)
    else:
        with pytest.raises(RuntimeError):
            demo.probe("https://backend.example", status)