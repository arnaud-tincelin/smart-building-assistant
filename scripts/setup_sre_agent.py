"""Configure the BuildingAssist Azure SRE Agent incident workflow.

ARM provisions the agent, identities, telemetry connectors, and alert. This script
applies the data-plane resources that ARM doesn't support: Code Access, the
security incident handler, and its Azure Monitor response plan.
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
HANDLER_NAME = "security-incident-handler"
RESPONSE_PLAN_NAME = "building-security-5xx"

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
4. Search open GitHub issues in the connected repository for the same failure.
   If one exists, add evidence to it instead of creating a duplicate.
5. If a code defect is confirmed and no matching issue exists, create exactly one
   issue titled `[SRE] Building access operations return HTTP 500` with sections:
   Summary, User impact, Timeline, Evidence, Root cause, Proposed fix, and
   Acceptance criteria. Include relevant non-sensitive incident IDs and source
   file paths. Acceptance criteria must require badge, mobile, and visitor flows
   to return successful 2xx responses and retain audit timestamps.

Do not change Azure resources, restart services, retry access requests, expose
secrets or personal data, or implement the fix. The GitHub issue is the handoff to
the coding agent and requires human assignment.
"""


def _azd_token(scope: str) -> str:
    environment = {**os.environ, "AZURE_DEV_USER_AGENT": "microsoft_foundry_skill"}
    result = subprocess.run(
        ["azd", "auth", "token", "--scope", scope, "--no-prompt"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
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
        "name": HANDLER_NAME,
        "type": "ExtendedAgent",
        "tags": ["buildingassist", "security"],
        "properties": {
            "instructions": HANDLER_INSTRUCTIONS,
            "handoffDescription": (
                "Investigates BuildingAssist access-control 5xx alerts and opens a repair issue."
            ),
            "handoffs": [],
            "tools": [
                "SearchMemory",
                "RunAzCliReadCommands",
                "QueryAppInsightsUsingAppId",
                "QueryLogAnalyticsByWorkspaceId",
                "FindConnectedGitHubRepo",
                "FetchGithubIssues",
                "CreateGithubIssue",
            ],
            "agentType": "Autonomous",
            "temperature": 0.2,
            "enableSkills": False,
            "allowedSkills": [],
        },
    }
    path = quote(HANDLER_NAME, safe="")
    _request_json("PUT", f"{endpoint}/api/v2/extendedAgent/agents/{path}", token, body)
    print(f"Configured SRE subagent {HANDLER_NAME!r}.")


def _ensure_response_plan(endpoint: str, token: str) -> None:
    body = {
        "name": RESPONSE_PLAN_NAME,
        "type": "IncidentFilter",
        "tags": ["buildingassist", "security"],
        "properties": {
            "incidentPlatform": "AzMonitor",
            "priorities": ["Sev2"],
            "handlingAgent": HANDLER_NAME,
            "agentMode": "Autonomous",
            "maxAutomatedInvestigationAttempts": 3,
            "isEnabled": True,
        },
    }
    path = quote(RESPONSE_PLAN_NAME, safe="")
    _request_json(
        "PUT",
        f"{endpoint}/api/v2/extendedAgent/incidentFilters/{path}",
        token,
        body,
    )
    print(f"Configured SRE response plan {RESPONSE_PLAN_NAME!r} for Azure Monitor Sev2.")


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
    if not all((subscription_id, resource_group, agent_name)):
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

    _ensure_handler(endpoint, sre_token)
    _ensure_response_plan(endpoint, sre_token)
    _ensure_repository(endpoint, sre_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())