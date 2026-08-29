"""
Tests for backend/api.py - the FastAPI layer over backend/. Uses FastAPI's
TestClient (no live server needed) and relies on the mock-data fallback
(backend/mock_data.py) since these tests don't require real artifact files,
FORTYGUARD_API_KEY, or GROQ_API_KEY - the same offline guarantee as the rest
of the suite.
"""
import pytest
from fastapi.testclient import TestClient

from backend.api import app

client = TestClient(app)


class TestMeta:
    def test_returns_mock_data_flag_and_counts(self):
        res = client.get("/api/meta")
        assert res.status_code == 200
        body = res.json()
        assert body["using_mock_data"] is True
        assert body["n_zones"] > 0
        assert body["n_critical_zones"] <= body["n_zones"]
        assert body["llm_configured"] is False


class TestRiskTable:
    def test_returns_all_zones_with_expected_fields(self):
        res = client.get("/api/risk-table")
        assert res.status_code == 200
        rows = res.json()
        assert len(rows) > 0
        row = rows[0]
        for field in ["zone_id", "grid_heat_risk", "heat_score", "demand_score",
                      "infra_score", "outage_score", "vuln_score"]:
            assert field in row


class TestCriticalZones:
    def test_default_threshold_matches_config(self):
        all_zones = client.get("/api/risk-table").json()
        critical = client.get("/api/critical-zones").json()
        expected = [z for z in all_zones if z["grid_heat_risk"] >= 40.0]
        assert len(critical) == len(expected)

    def test_custom_threshold_filters_correctly(self):
        res = client.get("/api/critical-zones?threshold=90")
        assert res.status_code == 200
        for zone in res.json():
            assert zone["grid_heat_risk"] >= 90


class TestMapData:
    def test_returns_grid_and_lines_geojson(self):
        res = client.get("/api/map")
        assert res.status_code == 200
        body = res.json()
        assert body["grid"]["type"] == "FeatureCollection"
        assert body["lines"]["type"] == "FeatureCollection"
        assert len(body["grid"]["features"]) > 0

    def test_grid_features_have_risk_score_attached(self):
        res = client.get("/api/map")
        features = res.json()["grid"]["features"]
        assert all("grid_heat_risk" in f["properties"] for f in features)


class TestPlan:
    def test_plan_respects_budget(self):
        res = client.get("/api/plan?budget=20000")
        assert res.status_code == 200
        body = res.json()
        assert body["total_cost"] <= 20000
        assert body["budget"] == 20000

    def test_negative_budget_rejected(self):
        res = client.get("/api/plan?budget=-100")
        assert res.status_code == 400

    def test_zero_budget_returns_empty_plan(self):
        res = client.get("/api/plan?budget=0")
        assert res.status_code == 200
        body = res.json()
        assert body["actions"] == []
        assert body["total_cost"] == 0

    def test_action_catalog_included(self):
        res = client.get("/api/plan?budget=50000")
        catalog = res.json()["action_catalog"]
        assert "crew_deployment" in catalog
        assert "cost" in catalog["crew_deployment"]


class TestExplainZone:
    def test_known_zone_returns_template_fallback_without_groq_key(self):
        zone_id = client.get("/api/risk-table").json()[0]["zone_id"]
        res = client.get(f"/api/explain/zone/{zone_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["zone_id"] == zone_id
        assert zone_id in body["explanation"]

    def test_unknown_zone_returns_404(self):
        res = client.get("/api/explain/zone/DOES_NOT_EXIST")
        assert res.status_code == 404


class TestExplainPlan:
    def test_returns_explanation_and_totals(self):
        res = client.post("/api/explain/plan", json={"budget": 50000})
        assert res.status_code == 200
        body = res.json()
        assert body["budget"] == 50000
        assert isinstance(body["explanation"], str) and body["explanation"]

    def test_zero_budget_explains_empty_plan_without_error(self):
        res = client.post("/api/explain/plan", json={"budget": 0})
        assert res.status_code == 200
        assert "no actions" in res.json()["explanation"].lower()

    def test_negative_budget_rejected(self):
        res = client.post("/api/explain/plan", json={"budget": -1})
        assert res.status_code == 400
