from __future__ import annotations

import pytest

from app import telemetry
from app.config import settings


@pytest.fixture(autouse=True)
def reset_tracing_state() -> None:
    telemetry._configured = False
    yield
    telemetry._configured = False


def test_tracing_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_tracing", False)

    assert telemetry.configure_tracing() is False


def test_tracing_configures_azure_monitor_without_content_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict = {}

    class Instrumentor:
        def instrument(self, **kwargs) -> None:  # noqa: ANN003
            calls["instrument"] = kwargs

    monkeypatch.setattr(settings, "enable_tracing", True)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=test")
    monkeypatch.setattr(
        telemetry,
        "configure_azure_monitor",
        lambda **kwargs: calls.update(monitor=kwargs),
    )
    monkeypatch.setattr(telemetry, "AIProjectInstrumentor", Instrumentor)

    assert telemetry.configure_tracing() is True
    assert telemetry.configure_tracing() is True
    assert calls["monitor"]["connection_string"] == "InstrumentationKey=test"
    assert calls["instrument"] == {
        "enable_content_recording": False,
        "enable_trace_context_propagation": True,
        "enable_baggage_propagation": False,
    }