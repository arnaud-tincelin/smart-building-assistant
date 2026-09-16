"""Azure Monitor OpenTelemetry setup for BuildingAssist."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from urllib.parse import urlsplit

from azure.ai.projects.telemetry import AIProjectInstrumentor
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import metrics, trace
from opentelemetry.trace import Span, SpanKind, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from .config import settings
from .models import ModelExecution

logger = logging.getLogger("buildingassist.telemetry")
_tracer = trace.get_tracer("buildingassist.foundry")
_meter = metrics.get_meter("buildingassist.foundry")
_duration = _meter.create_histogram("gen_ai.client.operation.duration", unit="s")
_tokens = _meter.create_histogram("gen_ai.client.token.usage", unit="{token}")
_propagator = TraceContextTextMapPropagator()

_configured = False


def configure_tracing() -> bool:
    """Configure Azure Monitor once; application spans handle the Responses call."""
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
    # Azure Monitor automatically enables this SDK wrapper; retain other Azure tracing.
    AIProjectInstrumentor().uninstrument()
    _configured = True
    logger.info("Application Insights tracing is enabled.")
    return True


def _agent_attributes() -> dict[str, str]:
    attributes = {
        "gen_ai.operation.name": "invoke_agent" if settings.agent_name else "chat",
        "gen_ai.provider.name": "azure.ai.projects",
        "gen_ai.request.model": settings.model_deployment,
    }
    if settings.agent_name:
        attributes["gen_ai.agent.name"] = settings.agent_name
    if host := urlsplit(settings.project_endpoint).hostname:
        attributes["server.address"] = host
    return attributes


@contextmanager
def trace_agent_call() -> Iterator[tuple[Span, dict[str, str]]]:
    if not _configured:
        yield trace.INVALID_SPAN, {}
        return

    attributes = _agent_attributes()
    target = settings.agent_name or settings.model_deployment
    name = f"{attributes['gen_ai.operation.name']} {target}"
    # The SDK Responses instrumentor reads .attributes on NonRecordingSpan.
    # Public Span methods preserve sampling without crashing or capturing message content.
    with _tracer.start_as_current_span(
        name, kind=SpanKind.CLIENT, attributes=attributes,
        record_exception=False, set_status_on_exception=False,
    ) as span:
        headers: dict[str, str] = {}
        _propagator.inject(headers)
        started_at = perf_counter()
        completed = False
        try:
            yield span, headers
            completed = True
        finally:
            if not completed:
                span.set_status(StatusCode.ERROR)
                if error := sys.exception():
                    attributes["error.type"] = type(error).__name__
                    span.set_attribute("error.type", type(error).__name__)
                _duration.record(perf_counter() - started_at, attributes=attributes)


def record_agent_execution(span: Span, execution: ModelExecution) -> None:
    if not _configured:
        return

    attributes = _agent_attributes()
    if execution.response_id:
        span.set_attribute("gen_ai.response.id", execution.response_id)
    if execution.reported_model:
        span.set_attribute("gen_ai.response.model", execution.reported_model)
        attributes["gen_ai.response.model"] = execution.reported_model
    _duration.record(execution.latency_ms / 1000, attributes=attributes)
    if execution.usage:
        for token_type, count in (
            ("input", execution.usage.input_tokens),
            ("output", execution.usage.output_tokens),
        ):
            if count is not None:
                span.set_attribute(f"gen_ai.usage.{token_type}_tokens", count)
                _tokens.record(count, attributes={**attributes, "gen_ai.token.type": token_type})