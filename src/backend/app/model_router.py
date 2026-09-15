"""Read and switch the Model Router routing mode on the Foundry deployment.

``properties.routing.mode`` is a management-plane setting, so this talks to ARM
rather than the inference endpoint. The app's managed identity needs read/write
access scoped to this deployment, and editing must be explicitly enabled.

Only the three documented modes are accepted, and the PUT body is rebuilt from
scratch rather than echoing the GET response, so nothing a caller sends can reach
ARM verbatim.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, get_args
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from pydantic import ValidationError

from .config import settings
from .models import RoutingMode, RoutingModeState

logger = logging.getLogger("buildingassist.modelrouter")

ARM_ENDPOINT = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
DEPLOYMENTS_API_VERSION = "2025-10-01-preview"

ROUTING_MODES: tuple[str, ...] = get_args(RoutingMode)

# Foundry documents the deployment as taking up to five minutes to pick up a new mode.
PROPAGATION_SECONDS = 300


class RouterControlError(RuntimeError):
    """Raised when the routing mode cannot be read or changed."""


class ModelRouterAdmin:
    """Minimal ARM client scoped to one model-router deployment."""

    def __init__(self, deployment_id: str) -> None:
        self._deployment_id = deployment_id.rstrip("/")
        self._credential: DefaultAzureCredential | None = None

    def _token(self) -> str:
        if self._credential is None:
            credential_kwargs = {}
            if settings.azure_client_id:
                credential_kwargs["managed_identity_client_id"] = settings.azure_client_id
            self._credential = DefaultAzureCredential(**credential_kwargs)
        try:
            return self._credential.get_token(ARM_SCOPE).token
        except AzureError as exc:
            raise RouterControlError("Could not authenticate to Azure Resource Manager.") from exc

    def _request(self, method: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = (
            f"{ARM_ENDPOINT}{self._deployment_id}"
            f"?{urlencode({'api-version': DEPLOYMENTS_API_VERSION})}"
        )
        request = Request(
            url,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed ARM host
                payload = json.loads(response.read())
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            logger.error("ARM %s failed with %s: %s", method, exc.code, detail)
            raise RouterControlError(
                f"Azure returned {exc.code} for the routing configuration request."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise RouterControlError("Could not reach Azure Resource Manager.") from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise RouterControlError("Azure returned an invalid routing configuration.") from exc
        if not isinstance(payload, dict):
            raise RouterControlError("Azure returned an invalid routing configuration.")
        return payload

    def get_mode(self) -> RoutingModeState:
        """Return the deployment's current routing mode and model subset."""
        deployment = self._request("GET")
        properties = deployment.get("properties") or {}
        if not isinstance(properties, dict):
            raise RouterControlError("Azure returned invalid deployment properties.")
        routing = properties.get("routing") or {}
        model = properties.get("model") or {}
        if not isinstance(routing, dict) or not isinstance(model, dict):
            raise RouterControlError("Azure returned an invalid routing configuration.")
        if model.get("name") != "model-router":
            raise RouterControlError("The configured deployment is not a Model Router.")
        subset_models = routing.get("models") or []
        if not isinstance(subset_models, list) or any(
            not isinstance(model, dict) for model in subset_models
        ):
            raise RouterControlError("Azure returned an invalid model subset.")
        subset = [model.get("name", "") for model in subset_models]
        # An unset routing block means the service default, which is Balanced.
        mode = routing.get("mode") or "balanced"
        try:
            return RoutingModeState.model_validate({
                "mode": mode.lower() if isinstance(mode, str) else mode,
                "editable": settings.enable_router_control,
                "explicitly_set": bool(routing.get("mode")),
                "model_name": model.get("name", ""),
                "model_version": model.get("version", ""),
                "model_subset": [name for name in subset if name],
                "propagation_seconds": PROPAGATION_SECONDS,
            })
        except ValidationError as exc:
            raise RouterControlError(
                "Azure returned an unsupported routing configuration."
            ) from exc

    def set_mode(self, mode: RoutingMode) -> RoutingModeState:
        """Switch the routing mode, preserving the deployment's other settings."""
        if not settings.enable_router_control:
            raise RouterControlError("Routing is read-only in this environment.")
        if mode not in ROUTING_MODES:
            raise RouterControlError(f"Unsupported routing mode: {mode}")

        current = self._request("GET")
        properties = current.get("properties") or {}
        if not isinstance(properties, dict):
            raise RouterControlError("Azure returned invalid deployment properties.")
        model = properties.get("model") or {}
        sku = current.get("sku") or {}
        if not isinstance(model, dict) or not isinstance(sku, dict):
            raise RouterControlError("Azure returned an invalid Model Router deployment.")
        if model.get("name") != "model-router" or not (
            model.get("format") and model.get("version") and sku.get("name")
            and sku.get("capacity") is not None
        ):
            raise RouterControlError("Azure did not return a valid Model Router deployment.")
        routing: dict[str, Any] = {"mode": mode}
        current_routing = properties.get("routing") or {}
        if not isinstance(current_routing, dict):
            raise RouterControlError("Azure returned an invalid routing configuration.")
        existing_subset = current_routing.get("models")
        if existing_subset:
            routing["models"] = existing_subset

        body: dict[str, Any] = {
            "sku": {"name": sku.get("name"), "capacity": sku.get("capacity")},
            "properties": {
                "model": {
                    "format": model.get("format"),
                    "name": model.get("name"),
                    "version": model.get("version"),
                },
                "routing": routing,
            },
        }
        if properties.get("raiPolicyName"):
            body["properties"]["raiPolicyName"] = properties["raiPolicyName"]
        if properties.get("versionUpgradeOption"):
            body["properties"]["versionUpgradeOption"] = properties["versionUpgradeOption"]

        self._request("PUT", body)
        logger.info("Model Router routing mode set to %s", mode)
        return self.get_mode()


@lru_cache(maxsize=1)
def get_admin() -> ModelRouterAdmin:
    """Return the shared admin client, or raise when the feature is not configured."""
    if not settings.model_deployment_resource_id:
        raise RouterControlError(
            "Routing mode control needs BUILDINGASSIST_MODEL_DEPLOYMENT_RESOURCE_ID."
        )
    return ModelRouterAdmin(settings.model_deployment_resource_id)


def known_mode() -> RoutingMode | None:
    """Read a snapshot for the answer; process-local state is stale across replicas."""
    try:
        return get_admin().get_mode().mode
    except RouterControlError as exc:
        logger.warning("Router metadata unavailable for this answer: %s", exc)
        return None
