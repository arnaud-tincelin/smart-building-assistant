"""Opt-in, reversible configuration fault for the BuildingAssist SRE chat demo."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SETTING = "BUILDINGASSIST_OPERATIONS_SOURCE"
GOOD_SOURCE = "simulator"
BAD_SOURCE = "bms-prod"
STATE_QUERY = (
    "{id:id,state:properties.provisioningState,latest:properties.latestRevisionName,"
    "ready:properties.latestReadyRevisionName,template:properties.template,"
    "mode:properties.configuration.activeRevisionsMode,"
    "ingress:properties.configuration.ingress}"
)


def run_cli(*arguments: str) -> str:
    executable = shutil.which(arguments[0])
    if not executable:
        raise RuntimeError(f"Required CLI not found on PATH: {arguments[0]}.")
    result = subprocess.run(
        (executable, *arguments[1:]), capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError(f"{arguments[0]} {arguments[1]} failed (exit {result.returncode}).")
    return result.stdout.strip()


def load_target(environment: str) -> tuple[list[str], str]:
    def value(name: str) -> str:
        result = run_cli(
            "azd", "env", "get-value", name, "--environment", environment, "--cwd", str(ROOT)
        )
        if not result:
            raise RuntimeError(f"Missing AZD value {name}.")
        return result

    subscription = value("AZURE_SUBSCRIPTION_ID")
    resource_group = value("AZURE_RESOURCE_GROUP")
    url = value("SERVICE_BACKEND_URL").rstrip("/")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or not parsed.hostname.endswith(".azurecontainerapps.io")
        or parsed.username or parsed.password or parsed.port
        or parsed.path or parsed.query or parsed.fragment
    ):
        raise RuntimeError("Expected a direct HTTPS Container Apps backend URL.")
    app_name = parsed.hostname.split(".")[0]
    if not app_name.startswith("ca-backend-"):
        raise RuntimeError("The selected environment does not identify a BuildingAssist backend.")
    target = [
        "--subscription", subscription, "--resource-group", resource_group, "--name", app_name
    ]
    return target, url


def read_state(target: list[str], url: str) -> dict:
    state = json.loads(run_cli(
        "az", "containerapp", "show", *target, "--query", STATE_QUERY, "--output", "json"
    ))
    if state["ingress"]["fqdn"] != urlsplit(url).hostname:
        raise RuntimeError("Live ingress does not match the selected environment.")
    if len(state["template"]["containers"]) != 1:
        raise RuntimeError("This demo only supports a single-container backend.")
    return state


def source_value(state: dict) -> str:
    settings = state["template"]["containers"][0].get("env", [])
    matches = [entry for entry in settings if entry["name"] == SETTING]
    if len(matches) > 1 or (matches and "secretRef" in matches[0]):
        raise RuntimeError("The demo setting must be a single nonsecret value.")
    return matches[0].get("value", "") if matches else GOOD_SOURCE


def unchanged_configuration(state: dict) -> dict:
    template = deepcopy(state["template"])
    template.pop("revisionSuffix", None)
    container = template["containers"][0]
    container["env"] = sorted(
        [entry for entry in container.get("env", []) if entry["name"] != SETTING],
        key=lambda entry: entry["name"],
    )
    return {"template": template, "ingress": state["ingress"], "mode": state["mode"]}


def is_ready(state: dict) -> bool:
    return bool(state.get("latest")) and (
        state["state"] == "Succeeded" and state["ready"] == state["latest"]
    )


def probe(url: str, expected_status: int) -> None:
    try:
        response = urlopen(f"{url}/operations/buildings", timeout=30)
    except HTTPError as error:
        response = error
    with response:
        if response.code != expected_status:
            raise RuntimeError(f"Expected HTTP {expected_status}; observed {response.code}.")
        if response.headers.get("X-Operations-Config") != "v1":
            raise RuntimeError("Deploy the configuration-demo backend before running this script.")
        if expected_status == 503 and response.headers.get("X-Error-Code") != "configuration_error":
            raise RuntimeError("The 503 is not the expected configuration fault.")
        if expected_status == 200:
            body = json.load(response)
            if body.get("simulation") is not True or not body.get("buildings"):
                raise RuntimeError("The building-data probe did not return the simulator data.")


def execute(action: str, environment: str, apply: bool = False) -> int:
    if action == "status" and apply:
        raise RuntimeError("--apply is only valid with break or fix.")
    target, url = load_target(environment)
    before = read_state(target, url)
    current = source_value(before)
    print(f"Target: {before['id']}")
    print(f"Backend: {url}")
    print(f"Latest: {before['latest']}; ready: {before['ready']}")
    if current not in (GOOD_SOURCE, BAD_SOURCE):
        raise RuntimeError(
            "Unexpected operations source; refusing to overwrite unrelated configuration."
        )
    print(f"{SETTING}={current}")
    if action == "status":
        if not is_ready(before):
            raise RuntimeError(
                "Revision rollout is pending; check status again after it completes."
            )
        probe(url, 200 if current == GOOD_SOURCE else 503)
        print("Verified the serving application's expected state.")
        return 0
    desired = BAD_SOURCE if action == "break" else GOOD_SOURCE
    print(f"Planned change: {SETTING}={desired}")
    print(f"Manual reset: demo_config.py fix --environment {environment} --apply")
    if not apply:
        print("Dry run only. Add --apply to change Azure configuration.")
        return 0
    if before["mode"] != "Single":
        raise RuntimeError("Single revision mode is required; traffic splitting is not changed.")
    if action == "break":
        if current != GOOD_SOURCE or not is_ready(before):
            raise RuntimeError(
                "Break requires a healthy, settled revision with simulator configuration."
            )
        probe(url, 200)
    elif current == GOOD_SOURCE:
        probe(url, 200)
        print("Already healthy; no update needed.")
        return 0
    run_cli(
        "az", "containerapp", "update", *target,
        "--set-env-vars", f"{SETTING}={desired}", "--output", "none",
    )
    after = read_state(target, url)
    if source_value(after) != desired:
        raise RuntimeError(
            "The requested setting was not persisted; inspect the app before retrying."
        )
    if unchanged_configuration(before) != unchanged_configuration(after):
        raise RuntimeError(
            "Other configuration changed concurrently; stop and inspect, do not auto-rollback."
        )
    print(f"Configuration updated at {datetime.now(UTC).isoformat()}")
    print(f"Revision: {after['latest']}")
    if not is_ready(after):
        print("Rollout is pending. Run status after it finishes; the configuration has changed.")
        return 2
    probe(url, 503 if action == "break" else 200)
    print("Fault verified. Start the investigation in SRE Agent chat." if action == "break"
          else "Recovery verified with a successful building-data request.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("break", "fix", "status"))
    parser.add_argument("--environment", required=True)
    parser.add_argument("--apply", action="store_true", help="Actually change the Azure setting.")
    args = parser.parse_args()
    try:
        return execute(args.action, args.environment, args.apply)
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"Demo stopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())