"""Exercise real Responses instrumentation without Azure calls or global test pollution."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("sampled", [False, True], ids=["sampled-out", "recorded"])
@pytest.mark.parametrize("failed", [False, True], ids=["success", "model-error"])
def test_agent_response_respects_sampling_and_content_privacy(
    sampled: bool, failed: bool
) -> None:
    script = """
import json
import os
import sys
import time

import httpx
from azure.ai.projects import AIProjectClient
from azure.ai.projects.telemetry import AIProjectInstrumentor
from azure.core.credentials import AccessToken
from azure.core.settings import settings as azure_settings
from azure.core.tracing.ext.opentelemetry_span import OpenTelemetrySpan
from openai import BadRequestError
from opentelemetry import baggage, context, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON

sampled = sys.argv[1] == "true"
failed = sys.argv[2] == "true"
exporter = InMemorySpanExporter()
provider = TracerProvider(sampler=ALWAYS_ON if sampled else ALWAYS_OFF)
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
azure_settings.tracing_implementation = OpenTelemetrySpan

from app import telemetry
from app.config import settings
from app.foundry_client import FoundryAgentClient

settings.enable_tracing = True
settings.model_deployment_resource_id = ""
settings.project_endpoint = "https://example.test/api/projects/test"
os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = "InstrumentationKey=test"
os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"
os.environ["AZURE_TRACING_GEN_AI_TRACE_CONTEXT_PROPAGATION_INCLUDE_BAGGAGE"] = "true"
telemetry.configure_azure_monitor = lambda **kwargs: AIProjectInstrumentor().instrument()
assert telemetry.configure_tracing()
assert not AIProjectInstrumentor().is_instrumented()

requests = []
def complete(request):
    requests.append(request)
    if failed:
        return httpx.Response(400, json={
            "error": {"message": "PRIVATE_ERROR", "type": "invalid_request_error",
                      "code": "test_failure"},
        })
    return httpx.Response(200, json={
        "id": "resp-sampling-test", "object": "response", "created_at": 1,
        "status": "completed", "model": "gpt-5.6-sol-2026-07-09",
        "output": [{
            "type": "message", "id": "msg-test", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": "PRIVATE_ANSWER", "annotations": []}],
        }],
        "usage": {
            "input_tokens": 20, "output_tokens": 3, "total_tokens": 23,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    })

class Credential:
    def get_token(self, *scopes, **kwargs):
        return AccessToken("test-token", int(time.time()) + 3600)

token = context.attach(baggage.set_baggage("private", "PRIVATE_BAGGAGE"))
try:
    with AIProjectClient(endpoint=settings.project_endpoint, credential=Credential()) as project:
        with project.get_openai_client(
            http_client=httpx.Client(transport=httpx.MockTransport(complete))
        ) as client:
            try:
                result = FoundryAgentClient()._create_response(
                    client, {"input": "PRIVATE_QUESTION", "model": "model-router"}
                )
                assert not failed
            except BadRequestError:
                assert failed
finally:
    context.detach(token)

if not failed:
    assert result.answer == "PRIVATE_ANSWER"
    assert result.execution.selected_model == "gpt-5.6-sol-2026-07-09"
assert len(requests) == 1
flags = int(requests[0].headers["traceparent"].rsplit("-", 1)[1], 16)
assert bool(flags & 1) == sampled
assert "baggage" not in requests[0].headers
spans = exporter.get_finished_spans()
if sampled:
    if failed:
        errors = [span for span in spans if span.status.status_code == trace.StatusCode.ERROR]
        assert len(errors) == 1
        assert errors[0].attributes["error.type"] == "BadRequestError"
    else:
        response_spans = [
            span for span in spans
            if span.attributes.get("gen_ai.response.id") == "resp-sampling-test"
        ]
        assert len(response_spans) == 1
        assert (
            response_spans[0].attributes["gen_ai.response.model"]
            == result.execution.selected_model
        )
        assert response_spans[0].attributes["gen_ai.usage.input_tokens"] == 20
    exported = json.dumps([
        {"attributes": dict(span.attributes),
         "events": [{"name": event.name, "attributes": dict(event.attributes)}
                    for event in span.events]}
        for span in spans
    ])
    assert "PRIVATE_QUESTION" not in exported
    assert "PRIVATE_ANSWER" not in exported
    assert "PRIVATE_ERROR" not in exported
    assert "PRIVATE_BAGGAGE" not in exported
else:
    assert not spans
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(sampled).lower(), str(failed).lower()],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
