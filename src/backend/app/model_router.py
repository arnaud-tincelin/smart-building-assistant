"""Read and switch the Model Router routing mode on the Foundry deployment.

``properties.routing.mode`` is a management-plane setting, so this talks to ARM
rather than the inference endpoint. The app's managed identity needs write access
to the deployment (``Cognitive Services Contributor`` on the Foundry account).

Only the three documented modes are accepted, and the PUT body is rebuilt from
scratch rather than echoing the GET response, so nothing a caller sends can reach
ARM verbatim.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Literal, get_args
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from azure.identity import DefaultAzureCredential

from .config import settings

logger = logging.getLogger("buildingassist.modelrouter")

ARM_ENDPOINT = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
DEPLOYMENTS_API_VERSION = "2025-10-01-preview"

RoutingMode = Literal["balanced", "cost", "quality"]
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
        return self._credential.get_token(ARM_SCOPE).token

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
                return json.loads(response.read() or b"{}")
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            logger.error("ARM %s failed with %s: %s", method, exc.code, detail)
            raise RouterControlError(
                f"Azure returned {exc.code} while updating the routing mode."
            ) from exc
        except URLError as exc:
            raise RouterControlError("Could not reach Azure Resource Manager.") from exc

    def get_mode(self) -> dict[str, Any]:
        """Return the deployment's current routing mode and model subset."""
        deployment = self._request("GET")
        properties = deployment.get("properties") or {}
        routing = properties.get("routing") or {}
        model = properties.get("model") or {}
        subset = [m.get("name", "") for m in routing.get("models") or []]
        # An unset routing block means the service default, which is Balanced.
        mode = (routing.get("mode") or "balanced").lower()
        _remember_mode(mode)
        return {
            "mode": mode,
            "explicitly_set": bool(routing.get("mode")),
            "model_name": model.get("name", ""),
            "model_version": model.get("version", ""),
            "model_subset": [name for name in subset if name],
        }

    def set_mode(self, mode: RoutingMode) -> dict[str, Any]:
        """Switch the routing mode, preserving the deployment's other settings."""
        if mode not in ROUTING_MODES:
            raise RouterControlError(f"Unsupported routing mode: {mode}")

        current = self._request("GET")
        properties = current.get("properties") or {}
        model = properties.get("model") or {}
        sku = current.get("sku") or {}
        routing: dict[str, Any] = {"mode": mode}
        existing_subset = (properties.get("routing") or {}).get("models")
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
    if not settings.enable_router_control:
        raise RouterControlError("Routing mode control is disabled for this environment.")
    if not settings.model_deployment_resource_id:
        raise RouterControlError(
            "Routing mode control needs BUILDINGASSIST_MODEL_DEPLOYMENT_RESOURCE_ID."
        )
    return ModelRouterAdmin(settings.model_deployment_resource_id)


_last_known_mode: str | None = None


def _remember_mode(mode: str) -> None:
    global _last_known_mode
    _last_known_mode = mode


def known_mode() -> str:
    """Best-known routing mode, without an ARM round trip on every answer."""
    return _last_known_mode or settings.model_router_mode.lower()
