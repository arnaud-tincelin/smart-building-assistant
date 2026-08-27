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
        "list_buildings",
        "get_building_information",
        "get_building_data",
    ]
    assert ACTION_MCP_TOOLS == ["create_work_order", "set_hvac_setpoint"]