"""Shared, conservative model attribution for both inference paths."""

from .models import AskMode, ModelExecution, RoutingMode, TokenUsage


def describe_execution(
    *,
    mode: AskMode,
    requested_model: str,
    reported_model: str | None,
    routing_mode: RoutingMode | None,
    latency_ms: int,
    response_id: str | None,
    usage: TokenUsage | None,
    tools_used: list[str],
) -> ModelExecution:
    reported_model = reported_model.strip() if reported_model else None
    selected_model = reported_model
    if reported_model and (
        (mode == "agents" and reported_model.casefold() == requested_model.casefold())
        or reported_model.casefold().startswith("model-router")
    ):
        selected_model = None

    path = "Foundry Agent Service" if mode == "agents" else "APIM AI Gateway"
    explanation = f"Called through {path} using deployment {requested_model}. "
    if selected_model:
        explanation += "The displayed model is the model reported in the final response. "
    else:
        explanation += "The service did not disclose the underlying model. "
    if mode == "gateway":
        explanation += "This path uses a fixed model deployment; Model Router is not used."
    elif routing_mode:
        explanation += (
            f"The shared router was configured to {routing_mode} at request start. "
            "Configuration changes can take up to five minutes to apply. "
        )
    else:
        explanation += "The shared router configuration was unavailable. "
    if mode == "agents":
        explanation += "The service does not expose its per-request model-selection reasoning."

    return ModelExecution(
        mode=mode,
        requested_model=requested_model,
        reported_model=reported_model,
        selected_model=selected_model,
        routing_mode=routing_mode,
        latency_ms=latency_ms,
        response_id=response_id,
        usage=usage,
        tools_used=tools_used,
        routing_explanation=explanation,
    )
