"""Configure the BuildingAssist Azure SRE Agent incident workflow.

ARM provisions the agent, identities, telemetry connectors, alerts, and scoped
permissions. This script applies the data-plane resources that ARM doesn't
support: Code Access, the repair skill, two handlers, and their response plans.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ARM_SCOPE = "https://management.azure.com/.default"
SRE_SCOPE = "https://azuresre.dev/.default"
API_VERSION = "2026-01-01"
SECURITY_HANDLER_NAME = "security-incident-handler"
SECURITY_RESPONSE_PLAN_NAME = "building-security-5xx"
CONFIG_HANDLER_NAME = "platform-config-operator"
CONFIG_RESPONSE_PLAN_NAME = "building-config-availability"
CONFIG_ROOT = Path(__file__).resolve().parents[1] / "sre-config"
CONFIG_SKILL_PATH = CONFIG_ROOT / "skills" / "repair-buildingassist-operations-config.md"
CONFIG_HANDLER_PATH = CONFIG_ROOT / "instructions" / "platform-config-operator.md"

SECURITY_TOOLS = [
    "SearchMemory",
    "SearchIncidentKnowledge",
    "RunAzCliReadCommands",
    "QueryAppInsightsByAppId",
    "QueryLogAnalyticsByWorkspaceId",
    "FindConnectedGitHubRepo",
    "ListDir",
    "FileSearch",
    "GrepSearch",
    "ReadFile",
    "RunInTerminal",
]
CONFIG_TOOLS = [
    "SearchMemory",
    "SearchIncidentKnowledge",
    "RunAzCliReadCommands",
    "RunAzCliWriteCommands",
    "QueryLogAnalyticsByWorkspaceId",
    "system-mcp-monitor_monitor_activitylog_list",
]

HANDLER_INSTRUCTIONS = """You investigate BuildingAssist Security & Access Control incidents.

When an Azure Monitor alert reports backend HTTP 5xx responses:
1. Query Application Insights and Log Analytics for the alert window. Find
   `Security control operation failed`, the exception traceback, operation names,
   request paths, and `SEC-` incident IDs. Never include visitor names, email
   addresses, credential IDs, access tokens, or other personal data in output.
2. Confirm whether `/security/access-requests`, `/security/visitors/check-in`, or
   both are affected. Correlate the first failure with recent deployments.
3. Inspect the connected smart-building repository. Compare the security domain
   event fields with the outbound audit adapter contract and prove the root cause
   from logs and source; do not guess.
4. Use `gh issue list` in the connected repository to search open GitHub issues
    for the same failure. If one exists, add evidence to it instead of creating a
    duplicate.
5. If a code defect is confirmed and no matching issue exists, use `gh issue create`
    to create exactly one
   issue titled `[SRE] Building access operations return HTTP 500` with sections:
   Summary, User impact, Timeline, Evidence, Root cause, Proposed fix, and
   Acceptance criteria. Include relevant non-sensitive incident IDs and source
   file paths. Acceptance criteria must require badge, mobile, and visitor flows
   to return successful 2xx responses and retain audit timestamps.

Do not change Azure resources, restart services, retry access requests, expose
secrets or personal data, or implement the fix. The GitHub issue is the handoff to
the coding agent and requires human assignment. If GitHub CLI authentication is
unavailable, report the exact command error instead of claiming an issue was filed.
"""


def _azd_token(scope: str) -> str:
    result = subprocess.run(
        ["azd", "auth", "token", "--scope", scope, "--no-prompt"],
        check=True,
        capture_output=True,
        text=True,
    )
    tokens = [line.strip() for line in result.stdout.splitlines() if line.count(".") == 2]
    if not tokens:
        raise RuntimeError(f"azd did not return a token for {scope!r}.")
    return max(tokens, key=len)


def _request_json(method: str, url: str, token: str, body: dict | None = None) -> dict:
    payload = json.dumps(body).encode() if body is not None else None
    request = Request(
        url,
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            content = response.read()
    except HTTPError as exc:
        message = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {message}") from exc
    return json.loads(content) if content else {}


def _render_config(path: Path, values: dict[str, str]) -> str:
    rendered = path.read_text(encoding="utf-8")
    for key, value in values.items():
        rendered = rendered.replace(f"${{{key}}}", value)
    if "${" in rendered:
        raise RuntimeError(f"Unresolved placeholder in {path}.")
    return rendered


def _load_skill(path: Path, values: dict[str, str]) -> tuple[str, str, str]:
    parts = _render_config(path, values).split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise RuntimeError(f"Invalid skill frontmatter in {path}.")

    metadata = {}
    for line in parts[1].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()

    try:
        return metadata["name"], metadata["description"], parts[2].strip()
    except KeyError as exc:
        raise RuntimeError(f"Skill {path} must define name and description.") from exc


def _repository_url() -> str:
    configured = os.environ.get("BUILDINGASSIST_GITHUB_REPOSITORY", "").strip()
    if configured:
        return configured if configured.startswith("https://") else f"https://github.com/{configured}"

    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    remote = result.stdout.strip()
    if remote.startswith("git@github.com:"):
        return f"https://github.com/{remote.removeprefix('git@github.com:').removesuffix('.git')}"
    if remote.startswith("https://github.com/"):
        return remote.removesuffix(".git")
    return ""


def _ensure_handler(endpoint: str, token: str) -> None:
    body = {
        "name": SECURITY_HANDLER_NAME,
        "type": "ExtendedAgent",
        "tags": ["buildingassist", "security"],
        "properties": {
            "instructions": HANDLER_INSTRUCTIONS,
            "handoffDescription": (
                "Investigates BuildingAssist access-control 5xx alerts and opens a repair issue."
            ),
            "handoffs": [],
            "tools": SECURITY_TOOLS,
            "agentType": "Autonomous",
            "temperature": 0.2,
            "enableSkills": False,
            "allowedSkills": [],
        },
    }
    path = quote(SECURITY_HANDLER_NAME, safe="")
    _request_json("PUT", f"{endpoint}/api/v2/extendedAgent/agents/{path}", token, body)
    print(f"Configured SRE subagent {SECURITY_HANDLER_NAME!r}.")


def _ensure_skill(endpoint: str, token: str, values: dict[str, str]) -> str:
    name, description, content = _load_skill(CONFIG_SKILL_PATH, values)
    body = {
        "name": name,
        "type": "Skill",
        "tags": ["buildingassist", "configuration"],
        "properties": {
            "name": name,
            "description": description,
            "tools": [],
            "skillContent": content,
            "additionalFiles": [],
            "sourcePluginInstallation": None,
        },
    }
    path = quote(name, safe="")
    _request_json("PUT", f"{endpoint}/api/v2/extendedAgent/skills/{path}", token, body)
    print(f"Configured SRE skill {name!r}.")
    return name


def _ensure_config_handler(
    endpoint: str,
    token: str,
    values: dict[str, str],
    skill_name: str,
) -> None:
    body = {
        "name": CONFIG_HANDLER_NAME,
        "type": "ExtendedAgent",
        "tags": ["buildingassist", "configuration"],
        "properties": {
            "instructions": _render_config(CONFIG_HANDLER_PATH, values),
            "handoffDescription": (
                "Diagnoses and repairs BuildingAssist Container App deployment configuration."
            ),
            "handoffs": [],
            "tools": CONFIG_TOOLS,
            "agentType": "Autonomous",
            "temperature": 0.1,
            "enableSkills": True,
            "allowedSkills": [skill_name],
        },
    }
    path = quote(CONFIG_HANDLER_NAME, safe="")
    _request_json("PUT", f"{endpoint}/api/v2/extendedAgent/agents/{path}", token, body)
    print(f"Configured SRE subagent {CONFIG_HANDLER_NAME!r}.")


def _ensure_response_plan(
    endpoint: str,
    token: str,
    *,
    plan_name: str,
    display_name: str,
    handler_name: str,
    priorities: list[str],
    title_contains: str,
) -> None:
    body = {
        "name": plan_name,
        "type": "IncidentFilter",
        "tags": ["buildingassist"],
        "properties": {
            "name": display_name,
            "incidentPlatform": "AzMonitor",
            "priorities": priorities,
            "titleContains": title_contains,
            "titleContainsAll": [],
            "titleContainsAny": [],
            "titleNotContains": [],
            "handlingAgent": handler_name,
            "agentMode": "autonomous",
            "maxAutomatedInvestigationAttempts": 3,
            "mergeEnabled": False,
            "mergeWindowHours": 3,
            "isEnabled": True,
        },
    }
    path = quote(plan_name, safe="")
    _request_json(
        "PUT",
        f"{endpoint}/api/v2/extendedAgent/incidentFilters/{path}",
        token,
        body,
    )
    print(f"Configured SRE response plan {plan_name!r} -> {handler_name!r}.")


def _delete_default_response_plan(endpoint: str, token: str) -> None:
    request = Request(
        f"{endpoint}/api/v1/incidentPlayground/filters/quickstart_response_plan",
        method="DELETE",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urlopen(request, timeout=30):
            pass
    except HTTPError as exc:
        if exc.code != 404:
            message = exc.read().decode(errors="replace")
            raise RuntimeError(
                f"DELETE quickstart response plan failed with HTTP {exc.code}: {message}"
            ) from exc


def _verify_tool_grants(endpoint: str, token: str) -> None:
    roster = _request_json("GET", f"{endpoint}/api/v2/agent/tools", token)
    tools = roster.get("data", roster.get("value", []))
    known = {tool.get("name") for tool in tools}
    if not known:
        print("SRE tool roster is unavailable; skipping tool-grant verification.")
        return

    for handler_name, granted in (
        (SECURITY_HANDLER_NAME, SECURITY_TOOLS),
        (CONFIG_HANDLER_NAME, CONFIG_TOOLS),
    ):
        missing = sorted(set(granted) - known)
        if missing:
            print(f"WARNING: {handler_name} has unknown tools: {', '.join(missing)}")
        else:
            print(f"Verified all tool grants for {handler_name!r}.")


def _ensure_repository(endpoint: str, token: str) -> None:
    repository_url = _repository_url()
    if not repository_url:
        print("No GitHub repository URL found; skipping SRE Code Access.")
        return

    domains = _request_json("GET", f"{endpoint}/api/v2/github/domains", token)
    configured_domains = domains.get("values", domains.get("value", []))
    if not configured_domains:
        oauth = _request_json("GET", f"{endpoint}/api/v2/github/oauth/config", token)
        oauth_url = oauth.get("oAuthUrl") or oauth.get("OAuthUrl")
        print("GitHub OAuth is required before Code Access can be configured.")
        if oauth_url:
            print(f"Authorize this agent once, then rerun azd provision: {oauth_url}")
        return

    repository_name = Path(repository_url).name
    body = {
        "name": repository_name,
        "type": "CodeRepo",
        "properties": {
            "url": repository_url,
            "type": "GitHub",
            "description": "BuildingAssist application, infrastructure, and operations source",
        },
    }
    path = quote(repository_name, safe="")
    _request_json("PUT", f"{endpoint}/api/v2/repos/{path}", token, body)
    test = _request_json("POST", f"{endpoint}/api/v2/repos/{path}/test", token)
    if not test.get("isSuccessful", False):
        raise RuntimeError(test.get("errorMessage") or "SRE Agent repository test failed.")
    print(f"Configured and tested SRE Code Access for {repository_url}.")


def main() -> int:
    subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
    resource_group = os.environ.get("AZURE_RESOURCE_GROUP", "")
    agent_name = os.environ.get("SRE_AGENT_NAME", "")
    backend_app_name = os.environ.get("BACKEND_CONTAINER_APP_NAME", "")
    if not all((subscription_id, resource_group, agent_name, backend_app_name)):
        print("SRE Agent outputs are unavailable; skipping incident workflow setup.")
        return 0

    try:
        arm_token = _azd_token(ARM_SCOPE)
        sre_token = _azd_token(SRE_SCOPE)
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"SRE data-plane authentication unavailable; setup skipped: {exc}", file=sys.stderr)
        return 0

    resource_url = (
        "https://management.azure.com"
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.App/agents/{agent_name}?api-version={API_VERSION}"
    )
    agent = _request_json("GET", resource_url, arm_token)
    endpoint = agent.get("properties", {}).get("agentEndpoint", "").rstrip("/")
    if not endpoint:
        raise RuntimeError("The SRE Agent endpoint is unavailable.")

    config_values = {"RG": resource_group, "BACKEND_APP": backend_app_name}
    config_skill_name = _ensure_skill(endpoint, sre_token, config_values)
    _ensure_handler(endpoint, sre_token)
    _ensure_config_handler(endpoint, sre_token, config_values, config_skill_name)
    _delete_default_response_plan(endpoint, sre_token)
    _ensure_response_plan(
        endpoint,
        sre_token,
        plan_name=SECURITY_RESPONSE_PLAN_NAME,
        display_name="BuildingAssist security HTTP 500",
        handler_name=SECURITY_HANDLER_NAME,
        priorities=["Sev2"],
        title_contains="security-5xx",
    )
    _ensure_response_plan(
        endpoint,
        sre_token,
        plan_name=CONFIG_RESPONSE_PLAN_NAME,
        display_name="BuildingAssist deployment configuration availability",
        handler_name=CONFIG_HANDLER_NAME,
        priorities=["Sev1"],
        title_contains="config-availability",
    )
    _ensure_repository(endpoint, sre_token)
    _verify_tool_grants(endpoint, sre_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())