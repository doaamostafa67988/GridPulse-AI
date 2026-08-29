"""
Tests for backend/llm_explain.py - the guardrail logic (numeric grounding,
self-attribution check) and the no-client fallback path. No real Groq call
is made anywhere in this file (client=None everywhere), so this runs the
same offline as the rest of the suite.
"""
import pandas as pd
import pytest

from backend.llm_explain import (
    build_zone_evidence,
    explain_plan,
    explain_zone,
    get_groq_client,
    validate_explanation,
)


@pytest.fixture
def sample_evidence() -> dict:
    return {
        "zone_id": "Z00001",
        "grid_heat_risk": 55.2,
        "heat_score": 70.0,
        "demand_score": 40.0,
        "infra_score": 30.0,
        "outage_score": 20.0,
        "vulnerability_score": 60.0,
        "nearby_transmission_lines": 2,
        "nearby_battery_sites": 1,
    }


class TestGetGroqClient:
    def test_returns_none_when_no_api_key(self, monkeypatch):
        monkeypatch.setattr("backend.llm_explain.GROQ_API_KEY", "")
        assert get_groq_client() is None


class TestBuildZoneEvidence:
    def test_assembles_expected_fields(self):
        risk_table = pd.DataFrame({
            "zone_id": ["Z00001"], "grid_heat_risk": [55.234], "heat_score": [70.0],
            "demand_score": [40.0], "infra_score": [30.0], "outage_score": [20.0],
            "vuln_score": [60.0],
        })
        lines_joined = pd.DataFrame({"zone_id": ["Z00001", "Z00001"], "OBJECTID": [1, 2]})
        battery_joined = pd.DataFrame({"zone_id": ["Z00001"], "n_battery_sites": [3]})

        evidence = build_zone_evidence("Z00001", risk_table, lines_joined, battery_joined)

        assert evidence["zone_id"] == "Z00001"
        assert evidence["grid_heat_risk"] == 55.23
        assert evidence["nearby_transmission_lines"] == 2
        assert evidence["nearby_battery_sites"] == 3

    def test_zero_batteries_when_zone_not_in_battery_joined(self):
        risk_table = pd.DataFrame({
            "zone_id": ["Z00002"], "grid_heat_risk": [10.0], "heat_score": [10.0],
            "demand_score": [10.0], "infra_score": [10.0], "outage_score": [10.0],
            "vuln_score": [10.0],
        })
        lines_joined = pd.DataFrame(columns=["zone_id", "OBJECTID"])
        battery_joined = pd.DataFrame({"zone_id": ["Z00001"], "n_battery_sites": [3]})

        evidence = build_zone_evidence("Z00002", risk_table, lines_joined, battery_joined)
        assert evidence["nearby_transmission_lines"] == 0
        assert evidence["nearby_battery_sites"] == 0


class TestValidateExplanation:
    def test_valid_grounded_explanation_passes(self, sample_evidence):
        text = (f"Zone {sample_evidence['zone_id']} scored {sample_evidence['grid_heat_risk']} "
                f"driven largely by a heat score of {sample_evidence['heat_score']} and "
                f"{sample_evidence['nearby_transmission_lines']} nearby transmission lines.")
        is_valid, reason = validate_explanation(text, sample_evidence)
        assert is_valid, reason

    def test_self_attribution_phrase_rejected(self, sample_evidence):
        text = "I calculated this zone's risk score based on the heat data."
        is_valid, reason = validate_explanation(text, sample_evidence)
        assert not is_valid
        assert "self-attribution" in reason

    def test_ungrounded_number_rejected(self, sample_evidence):
        text = "This zone has a risk score of 999.9, which is very high."
        is_valid, reason = validate_explanation(text, sample_evidence)
        assert not is_valid
        assert "ungrounded number" in reason

    def test_bare_small_integers_are_exempt(self, sample_evidence):
        text = "This zone was flagged based on 5 different component scores."
        is_valid, reason = validate_explanation(text, sample_evidence)
        assert is_valid, reason

    def test_shorthand_k_suffix_matches_real_evidence_value(self):
        evidence = {"zone_id": "Z1", "cost": 50000}
        text = "The selected action costs $50K under the budget."
        is_valid, reason = validate_explanation(text, evidence)
        assert is_valid, reason

    def test_zone_id_digits_not_misread_as_number(self, sample_evidence):
        text = f"Zone {sample_evidence['zone_id']} was flagged for review."
        is_valid, reason = validate_explanation(text, sample_evidence)
        assert is_valid, reason


class TestExplainZoneFallback:
    def test_returns_template_when_client_is_none(self, sample_evidence):
        text = explain_zone(None, sample_evidence)
        assert sample_evidence["zone_id"] in text
        assert "GROQ_API_KEY not set" in text


class TestExplainPlanFallback:
    def test_returns_template_when_client_is_none(self):
        plan_df = pd.DataFrame([
            {"zone_id": "Z00001", "action": "crew_deployment", "cost": 8000, "value": 12.5},
        ])
        text = explain_plan(None, plan_df, total_cost=8000, total_value=12.5, budget=50000)
        assert "$50,000" in text
        assert "GROQ_API_KEY not set" in text

    def test_empty_plan_template_still_renders(self):
        plan_df = pd.DataFrame(columns=["zone_id", "action", "cost", "value"])
        text = explain_plan(None, plan_df, total_cost=0, total_value=0.0, budget=50000)
        assert "0 action(s)" in text
