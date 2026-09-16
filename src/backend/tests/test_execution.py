import pytest

from app.execution import describe_execution


@pytest.mark.parametrize("reported", [None, "", "model-router", "model-router-2025-11-18"])
@pytest.mark.parametrize("mode", ["agents", "gateway"])
def test_deployment_name_is_never_claimed_as_the_selected_model(reported, mode) -> None:
    execution = describe_execution(
        mode=mode, requested_model="model-router", reported_model=reported,
        routing_mode=None, latency_ms=12, response_id=None, usage=None, tools_used=[],
    )
    assert execution.selected_model is None
    assert execution.usage is None
    assert execution.routing_mode is None
    assert "did not disclose" in execution.routing_explanation


def test_selected_model_is_taken_only_from_the_response() -> None:
    execution = describe_execution(
        mode="agents", requested_model="model-router",
        reported_model="gpt-5.6-sol-2026-07-09", routing_mode="cost",
        latency_ms=100, response_id="completion-1", usage=None, tools_used=[],
    )
    assert execution.selected_model == "gpt-5.6-sol-2026-07-09"
    assert execution.mode == "agents"
    assert execution.routing_mode == "cost"
    assert "does not expose its per-request" in execution.routing_explanation


@pytest.mark.parametrize("reported", ["gpt-5-mini", "gpt-5-mini-2025-08-07"])
def test_fixed_model_is_reported_without_router_metadata(reported) -> None:
    execution = describe_execution(
        mode="gateway", requested_model="gpt-5-mini", reported_model=reported,
        routing_mode=None, latency_ms=100, response_id="completion-2", usage=None, tools_used=[],
    )
    assert execution.selected_model == reported
    assert execution.routing_mode is None
    assert "Model Router is not used" in execution.routing_explanation
    assert "configuration was unavailable" not in execution.routing_explanation
