from app.agent_policy import (
    ACTION_MCP_TOOLS,
    AGENT_INSTRUCTIONS,
    READ_ONLY_MCP_TOOLS,
    UNKNOWN_RESPONSE,
)


def test_agent_policy_is_closed_book_with_exact_unknown_response() -> None:
    assert UNKNOWN_RESPONSE == "i don't know"
    assert "Use only information returned by the connected MCP tools" in AGENT_INSTRUCTIONS
    assert "Never answer factual questions from model knowledge" in AGENT_INSTRUCTIONS
    assert "reply with exactly: i don't know" in AGENT_INSTRUCTIONS


def test_agent_policy_defines_separate_information_and_data_tools() -> None:
    assert READ_ONLY_MCP_TOOLS == [
        "operations_listBuildings",
        "operations_getBuildingInformation",
        "operations_getBuildingData",
    ]
    assert ACTION_MCP_TOOLS == [
        "operations_createWorkOrder",
        "operations_setHvacSetpoint",
    ]


def test_agent_policy_requires_rules_and_live_data_for_compliance_questions() -> None:
    assert "compliance, threshold, limit, or out-of-range questions" in AGENT_INSTRUCTIONS
    assert "always use both sources" in AGENT_INSTRUCTIONS
    assert "knowledge_base_retrieve" in AGENT_INSTRUCTIONS
    assert "operations_getBuildingData" in AGENT_INSTRUCTIONS
    assert "applicable retrieved rule and matching units" in AGENT_INSTRUCTIONS
    assert (
        "current value, threshold, compliant/non-compliant result, live as_of"
        in AGENT_INSTRUCTIONS
    )
