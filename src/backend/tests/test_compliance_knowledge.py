from __future__ import annotations

import importlib.util
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[3]
SETUP_FOUNDRY_IQ = REPOSITORY_ROOT / "scripts" / "setup_foundry_iq.py"
COMPLIANCE_SOURCE = "sample-docs/building-compliance-rules.md"


def _load_setup_module():
    spec = importlib.util.spec_from_file_location(
        "setup_foundry_iq", SETUP_FOUNDRY_IQ)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_foundry_iq_indexes_compliance_rules_for_live_metrics() -> None:
    chunks = _load_setup_module()._document_chunks(REPOSITORY_ROOT / "sample-docs")
    compliance_content = "\n".join(
        chunk["content"] for chunk in chunks if chunk["source"] == COMPLIANCE_SOURCE
    )

    assert compliance_content
    for metric in (
        "temperature_c",
        "co2_ppm",
        "relative_humidity_percent",
        "occupancy_percent",
        "current_power_kw",
        "energy_today_kwh",
        "energy_this_week_kwh",
        "indoor_temperature_c",
        "outdoor_temperature_c",
        "hvac_setpoint_c",
        "renewable_share_percent",
        "setpoint_c",
    ):
        assert metric in compliance_content


def test_foundry_iq_knowledge_base_has_chat_model(monkeypatch) -> None:
    module = _load_setup_module()
    monkeypatch.setattr(
        module,
        "KNOWLEDGE_MODEL_RESOURCE_URI",
        "https://buildingassist.openai.azure.com",
    )

    knowledge_base = module._knowledge_base()
    model_parameters = knowledge_base.models[0].azure_open_ai_parameters

    assert model_parameters.resource_url == "https://buildingassist.openai.azure.com"
    assert model_parameters.deployment_name == "gpt-5-mini"
    assert model_parameters.model_name == "gpt-5-mini"


def test_foundry_iq_knowledge_base_has_explicit_retrieval_settings() -> None:
    module = _load_setup_module()

    payload = module._knowledge_base_preview_payload(
        {"name": "buildingassist-knowledge"})

    assert payload["retrievalReasoningEffort"] == {"kind": "low"}
    assert payload["outputMode"] == "extractiveData"
