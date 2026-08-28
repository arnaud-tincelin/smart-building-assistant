"""Configure managed-identity OTLP export from AI Gateway to Application Insights."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from azure.identity import DefaultAzureCredential

ARM_ENDPOINT = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
APP_INSIGHTS_API_VERSION = "2020-02-02"
APP_INSIGHTS_PATCH_API_VERSION = "2020-02-02-preview"
AI_GATEWAY_API_VERSION = "2025-09-01-preview"
ROLE_ASSIGNMENT_API_VERSION = "2022-04-01"
MONITORING_METRICS_PUBLISHER_ROLE_ID = "3913510d-42f4-4e42-8a64-420c390055eb"
OTLP_AUDIENCE = "https://monitor.azure.com"


def _arm_request(
    token: str,
    method: str,
    resource_id: str,
    api_version: str,
    body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    allow_not_found: bool = False,
) -> dict[str, Any]:
    url = f"{ARM_ENDPOINT}{resource_id}?{urlencode({'api-version': api_version})}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers or {})
    request = Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed ARM host
            payload = response.read()
    except HTTPError as exc:
        if allow_not_found and exc.code == 404:
            return {}
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"ARM {method} failed for {resource_id}: HTTP {exc.code}: {detail}"
        ) from exc
    return json.loads(payload) if payload else {}


def _subscription_id(resource_id: str) -> str:
    parts = resource_id.strip("/").split("/")
    if len(parts) < 2 or parts[0].lower() != "subscriptions":
        raise RuntimeError(f"Invalid Azure resource ID: {resource_id}")
    return parts[1]


def _get_otlp_configuration(
    token: str,
    app_insights_id: str,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    component = _arm_request(
        token,
        "GET",
        app_insights_id,
        APP_INSIGHTS_API_VERSION,
    )
    if component.get("properties", {}).get("AzureMonitorWorkspaceIngestionMode") != "Enabled":
        _arm_request(
            token,
            "PATCH",
            app_insights_id,
            APP_INSIGHTS_PATCH_API_VERSION,
            {"properties": {"AzureMonitorWorkspaceIngestionMode": "Enabled"}},
        )

    required = (
        "OTLPMetricsEndpoint",
        "OTLPLogsEndpoint",
        "OTLPTracesEndpoint",
        "DataCollectionRuleResourceId",
    )
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        component = _arm_request(
            token,
            "GET",
            app_insights_id,
            APP_INSIGHTS_API_VERSION,
        )
        properties = component.get("properties", {})
        if all(properties.get(name) for name in required):
            return properties
        time.sleep(3)

    raise RuntimeError(
        "Application Insights OTLP endpoints were not ready within 180 seconds.")


def _grant_metrics_publisher(
    token: str,
    data_collection_rule_id: str,
    gateway_id: str,
    gateway_principal_id: str,
) -> None:
    subscription_id = _subscription_id(data_collection_rule_id)
    role_definition_id = (
        f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization/"
        f"roleDefinitions/{MONITORING_METRICS_PUBLISHER_ROLE_ID}"
    )
    assignment_name = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{data_collection_rule_id}|{gateway_id}|{MONITORING_METRICS_PUBLISHER_ROLE_ID}",
    )
    _arm_request(
        token,
        "PUT",
        (
            f"{data_collection_rule_id}/providers/Microsoft.Authorization/"
            f"roleAssignments/{assignment_name}"
        ),
        ROLE_ASSIGNMENT_API_VERSION,
        {
            "properties": {
                "principalId": gateway_principal_id,
                "principalType": "ServicePrincipal",
                "roleDefinitionId": role_definition_id,
            }
        },
    )


def _configure_exporter(
    token: str,
    gateway_id: str,
    app_insights_id: str,
    otlp: dict[str, Any],
) -> None:
    exporter_id = f"{gateway_id}/workspaces/default/telemetryExporters/appinsights"
    existing = _arm_request(
        token,
        "GET",
        exporter_id,
        AI_GATEWAY_API_VERSION,
        allow_not_found=True,
    )
    existing_kind = existing.get("properties", {}).get("kind", "")
    if existing and existing_kind.lower() != "opentelemetry":
        _arm_request(
            token,
            "DELETE",
            exporter_id,
            AI_GATEWAY_API_VERSION,
            extra_headers={"If-Match": "*"},
        )

    _arm_request(
        token,
        "PUT",
        exporter_id,
        AI_GATEWAY_API_VERSION,
        {
            "properties": {
                "kind": "OpenTelemetry",
                "payloadCapture": False,
                "applicationInsights": {"resourceId": app_insights_id},
                "openTelemetry": {
                    "metricsEndpoint": otlp["OTLPMetricsEndpoint"],
                    "logsEndpoint": otlp["OTLPLogsEndpoint"],
                    "tracesEndpoint": otlp["OTLPTracesEndpoint"],
                    "managedIdentity": {"resource": OTLP_AUDIENCE},
                },
            }
        },
    )


def main() -> int:
    gateway_id = os.environ.get("AI_GATEWAY_RESOURCE_ID", "")
    app_insights_id = os.environ.get("APPLICATIONINSIGHTS_RESOURCE_ID", "")
    if not gateway_id or not app_insights_id:
        print(
            "AI_GATEWAY_RESOURCE_ID or APPLICATIONINSIGHTS_RESOURCE_ID is not set; "
            "skipping AI Gateway telemetry setup.",
            file=sys.stderr,
        )
        return 0

    credential = DefaultAzureCredential()
    try:
        token = credential.get_token(ARM_SCOPE).token
        otlp = _get_otlp_configuration(token, app_insights_id)
        gateway = _arm_request(
            token,
            "GET",
            gateway_id,
            AI_GATEWAY_API_VERSION,
        )
        principal_id = gateway.get("identity", {}).get("principalId")
        if not principal_id:
            raise RuntimeError(
                "AI Gateway system-assigned identity has no principal ID.")

        _grant_metrics_publisher(
            token,
            otlp["DataCollectionRuleResourceId"],
            gateway_id,
            principal_id,
        )
        _configure_exporter(token, gateway_id, app_insights_id, otlp)
    finally:
        credential.close()

    print("Configured AI Gateway OTLP telemetry to Application Insights.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
