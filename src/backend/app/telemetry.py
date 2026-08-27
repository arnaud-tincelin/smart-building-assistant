"""Azure Monitor OpenTelemetry setup for BuildingAssist."""

from __future__ import annotations

import logging
import os

from azure.ai.projects.telemetry import AIProjectInstrumentor
from azure.monitor.opentelemetry import configure_azure_monitor

from .config import settings

logger = logging.getLogger("buildingassist.telemetry")

_configured = False


def configure_tracing() -> bool:
    """Configure Azure Monitor and Azure AI Projects tracing once per process."""
    global _configured

    if _configured:
        return True
    if not settings.enable_tracing:
        return False

    connection_string = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not connection_string:
        logger.warning("Tracing is enabled but APPLICATIONINSIGHTS_CONNECTION_STRING is missing.")
        return False

    os.environ.setdefault("AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING", "true")
    os.environ.setdefault("OTEL_SERVICE_NAME", "buildingassist-backend")

    configure_azure_monitor(
        connection_string=connection_string,
        logger_name="buildingassist",
    )
    AIProjectInstrumentor().instrument(
        enable_content_recording=False,
        enable_trace_context_propagation=True,
        enable_baggage_propagation=False,
    )
    _configured = True
    logger.info("Application Insights tracing is enabled.")
    return True