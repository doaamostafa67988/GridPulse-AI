"""
Tests for backend/graph.py - the LangGraph agentic workflow (Texas pilot).

Covers each node in isolation (fast, no I/O) plus one full end-to-end
app.invoke() run with every external dependency (FortyGuard, the demand
model, and the data_access loaders for transmission lines / EJScreen)
mocked or monkeypatched, so the suite needs no API key, no downloaded data
files, and no network access to run.
"""
import pandas as pd
import pytest

from backend import graph as g
from backend.risk_engine import build_risk_table, score_against_reference_range, normalize_0_100


# ============ Individual node / function tests ============

class TestHeatAgent:
    def test_returns_one_row_per_zone(self, mock_fg_client, sample_grid):
        state = {"fg_client": mock_fg_client, "pilot_aoi": {"type": "FeatureCollection", "features": []},
                  "grid": sample_grid, "target_date": "2026-07-15"}
        result = g.heat_agent(state)
        assert set(result["live_heat"]["zone_id"]) == set(sample_grid["zone_id"])
        assert "heat_raw_f" in result["live_heat"].columns

    def test_calls_fortyguard_with_the_given_aoi_and_date(self, mock_fg_client, sample_grid):
        aoi = {"type": "FeatureCollection", "features": [{"type": "Feature"}]}
        state = {"fg_client": mock_fg_client, "pilot_aoi": aoi, "grid": sample_grid, "target_date": "2026-07-20"}
        g.heat_agent(state)
        assert mock_fg_client.calls[-1]["polygon_aoi"] == aoi
        assert mock_fg_client.calls[-1]["start_date"] == "2026-07-20"

    def test_defaults_to_yesterday_when_no_target_date(self, mock_fg_client, sample_grid):
        from datetime import date, timedelta
        state = {"fg_client": mock_fg_client, "pilot_aoi": {"type": "FeatureCollection", "features": []},
                  "grid": sample_grid, "target_date": None}
        g.heat_agent(state)
        expected = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert mock_fg_client.calls[-1]["start_date"] == expected


class TestDemandForecastAgent:
    def test_falls_back_to_linear_when_no_multivariate_model(self, mock_fg_client, mock_demand_model, sample_live_heat):
        """Texas-specific: state["demand_model"] is a bundle dict, not a
        bare estimator - with no multivariate model configured (the default
        MockDemandBundle), predict_demand_stress must fall back to
        "linear" rather than erroring."""
        state = {
            "demand_model": mock_demand_model,
            "baseline_demand_mw": 10000.0,
            "live_heat": sample_live_heat,
            "demand_historical_range": (-20.0, 20.0),
            "fg_client": mock_fg_client,
            "pilot_aoi": {"type": "FeatureCollection", "features": [{"type": "Feature"}]},
        }
        result = g.demand_forecast_agent(state)

        mean_temp = sample_live_heat["heat_raw_f"].mean()
        expected_predicted = mean_temp * 50 + 5000
        expected_stress_pct = (expected_predicted - 10000.0) / 10000.0 * 100
        assert result["demand_stress_pct"] == pytest.approx(expected_stress_pct)
        assert result["demand_model_used"] == "linear (fallback)"

    def test_demand_score_is_never_zero_purely_from_being_constant_across_zones(
        self, mock_fg_client, mock_demand_model, sample_live_heat
    ):
        """Regression test for the real bug this project hit: demand is a
        single system-level number (same for every zone), so scoring it via
        normalize_0_100 across zones always gave 0. score_against_reference_range
        (used inside demand_forecast_agent) must NOT reproduce that bug."""
        state = {
            "demand_model": mock_demand_model, "baseline_demand_mw": 10000.0,
            "live_heat": sample_live_heat, "demand_historical_range": (-20.0, 20.0),
            "fg_client": mock_fg_client,
            "pilot_aoi": {"type": "FeatureCollection", "features": [{"type": "Feature"}]},
        }
        result = g.demand_forecast_agent(state)
        assert 0.0 <= result["demand_score"] <= 100.0
        if result["demand_stress_pct"] > -20.0:
            assert result["demand_score"] > 0.0


class TestGridAssetAndOutageAgents:
    def test_grid_asset_agent_counts_lines_per_zone(self, monkeypatch, sample_grid, sample_lines_joined):
        monkeypatch.setattr(g.data_access, "load_transmission_lines", lambda: _lines_gdf_for(sample_lines_joined, sample_grid))
        result = g.grid_asset_agent({"grid": sample_grid})
        counts = result["lines_joined"].groupby("zone_id").size()
        assert counts.get("Z00000", 0) == 2
        assert counts.get("Z00001", 0) == 1
        assert "Z00002" not in counts.index

    def test_outage_agent_scores_the_broadcast_county_total_no_spatial_join(self):
        """Texas-specific: EAGLE-I has no per-event geometry, so
        outage_agent doesn't do a spatial join at all - it just scores the
        single county-level total against the cross-county reference range."""
        state = {"pilot_total_outage_customers": 5_000_000.0, "outage_reference_range": (0.0, 10_000_000.0)}
        result = g.outage_agent(state)
        assert result["outage_score"] == pytest.approx(50.0)

    def test_outage_agent_clips_to_0_100(self):
        state = {"pilot_total_outage_customers": 999_999_999.0, "outage_reference_range": (0.0, 10_000_000.0)}
        assert g.outage_agent(state)["outage_score"] == 100.0


def _lines_gdf_for(joined_df: pd.DataFrame, grid) -> "gpd.GeoDataFrame":
    """Build a fake transmission-lines GeoDataFrame whose lines actually
    pass through the zones sample_lines_joined claims they do - a real
    LineString per row, positioned inside the matching grid cell."""
    import geopandas as gpd
    from shapely.geometry import LineString

    zone_bounds = {row["zone_id"]: row["geometry"].bounds for _, row in grid.iterrows()}
    geoms = []
    for _, row in joined_df.iterrows():
        minx, miny, maxx, maxy = zone_bounds[row["zone_id"]]
        w, h = maxx - minx, maxy - miny
        geoms.append(LineString([(minx + 0.25 * w, miny + 0.25 * h), (minx + 0.75 * w, miny + 0.75 * h)]))
    return gpd.GeoDataFrame({"OBJECTID": joined_df["OBJECTID"]}, geometry=geoms, crs="EPSG:4326")


# ============ Risk engine math (sanity checks against the notebook's own numbers) ============

class TestRiskEngineMath:
    def test_build_risk_table_broadcasts_demand_with_no_infra_weights(
        self, sample_grid, sample_live_heat, sample_vulnerability_joined, sample_lines_joined,
    ):
        """With no infra_weights supplied, demand_score is identical for
        every zone (flat broadcast) - matches the California version's
        original behavior and is the explicit fallback in the Texas one."""
        demand_score = 12.78514
        outage_score = 35.0
        risk_table = build_risk_table(
            sample_grid, sample_live_heat, sample_vulnerability_joined,
            sample_lines_joined, demand_score, outage_score, infra_weights=None,
        )

        top = risk_table.iloc[0]
        assert top["zone_id"] == "Z00000"  # hottest, most infra, most vulnerable
        assert top["heat_score"] == pytest.approx(100.0)
        assert top["infra_score"] == pytest.approx(100.0)
        assert top["vuln_score"] == pytest.approx(100.0)
        assert top["demand_score"] == pytest.approx(demand_score)
        assert (risk_table["demand_score"] == pytest.approx(demand_score)).all()
        assert (risk_table["outage_score"] == pytest.approx(outage_score)).all()

        expected_risk = 100 * 0.30 + demand_score * 0.25 + 100 * 0.20 + outage_score * 0.15 + 100 * 0.10
        assert top["grid_heat_risk"] == pytest.approx(expected_risk)

    def test_infra_weights_redistribute_demand_score_preserving_aoi_average(
        self, sample_grid, sample_live_heat, sample_vulnerability_joined,
        sample_lines_joined, sample_infra_weights,
    ):
        """Texas-specific: with infra_weights supplied, demand_score should
        vary across zones (higher where infra_weight is higher) while the
        AOI-wide average stays equal to the original system-wide value."""
        demand_score = 40.0
        risk_table = build_risk_table(
            sample_grid, sample_live_heat, sample_vulnerability_joined,
            sample_lines_joined, demand_score, outage_score=20.0, infra_weights=sample_infra_weights,
        )
        assert risk_table["demand_score"].nunique() > 1
        assert risk_table["demand_score"].mean() == pytest.approx(demand_score)
        z0 = risk_table.loc[risk_table["zone_id"] == "Z00000", "demand_score"].iloc[0]
        z2 = risk_table.loc[risk_table["zone_id"] == "Z00002", "demand_score"].iloc[0]
        assert z0 > z2
        assert z2 == pytest.approx(0.0)  # zero infra_weight -> zero multiplier

    def test_normalize_constant_column_returns_all_zeros(self):
        constant = pd.Series([42.0, 42.0, 42.0])
        result = normalize_0_100(constant)
        assert (result == 0.0).all()

    def test_score_against_reference_range_clips_to_0_100(self):
        assert score_against_reference_range(-999.0, (-20.0, 20.0)) == 0.0
        assert score_against_reference_range(999.0, (-20.0, 20.0)) == 100.0
        assert score_against_reference_range(0.0, (-20.0, 20.0)) == pytest.approx(50.0)


# ============ Routing logic ============

class TestRouteByRisk:
    def test_escalates_when_a_zone_is_at_or_above_threshold(self):
        risk_table = pd.DataFrame({"zone_id": ["Z00000"], "grid_heat_risk": [50.0]})
        assert g.route_by_risk({"risk_threshold": 40.0, "risk_table": risk_table}) == "escalated"

    def test_monitors_when_every_zone_is_below_threshold(self):
        risk_table = pd.DataFrame({"zone_id": ["Z00000"], "grid_heat_risk": [10.0]})
        assert g.route_by_risk({"risk_threshold": 40.0, "risk_table": risk_table}) == "monitor_only"

    def test_boundary_is_inclusive(self):
        risk_table = pd.DataFrame({"zone_id": ["Z00000"], "grid_heat_risk": [40.0]})
        assert g.route_by_risk({"risk_threshold": 40.0, "risk_table": risk_table}) == "escalated"


# ============ Full graph, end-to-end, fully mocked ============

class TestFullGraphEndToEnd:
    @pytest.fixture(autouse=True)
    def _patch_data_sources(self, monkeypatch, sample_grid):
        """Every node that hits data_access in the real pipeline gets a
        fixture-backed fake instead, so the full graph.invoke() below never
        touches a real file or network call."""
        monkeypatch.setattr(g.data_access, "load_transmission_lines",
                             lambda: _lines_gdf_for(pd.DataFrame({"zone_id": ["Z00000"], "OBJECTID": [1]}), sample_grid))
        monkeypatch.setattr(g.data_access, "load_ejscreen",
                             lambda: _ejscreen_gdf_for(sample_grid))

    def test_escalates_end_to_end_when_heat_is_high(self, mock_fg_client, mock_demand_model, sample_grid):
        app = g.build_graph()
        result = app.invoke({
            "risk_threshold": 10.0,  # low threshold so a hot mocked day escalates
            "target_date": "2026-07-15",
            "fg_client": mock_fg_client,
            "pilot_aoi": {"type": "FeatureCollection", "features": [{"type": "Feature"}]},
            "grid": sample_grid,
            "demand_model": mock_demand_model,
            "baseline_demand_mw": 10000.0,
            "demand_historical_range": (-20.0, 20.0),
            "pilot_total_outage_customers": 5_000_000.0,
            "outage_reference_range": (0.0, 10_000_000.0),
        })

        assert result["status"] == "escalated"
        assert not result["critical_zones"].empty
        assert "grid_heat_risk" in result["risk_table"].columns
        assert len(result["risk_table"]) == len(sample_grid)

    def test_monitors_end_to_end_when_threshold_is_unreachably_high(self, mock_fg_client, mock_demand_model, sample_grid):
        app = g.build_graph()
        result = app.invoke({
            "risk_threshold": 99999.0,
            "target_date": "2026-07-15",
            "fg_client": mock_fg_client,
            "pilot_aoi": {"type": "FeatureCollection", "features": [{"type": "Feature"}]},
            "grid": sample_grid,
            "demand_model": mock_demand_model,
            "baseline_demand_mw": 10000.0,
            "demand_historical_range": (-20.0, 20.0),
            "pilot_total_outage_customers": 5_000_000.0,
            "outage_reference_range": (0.0, 10_000_000.0),
        })

        assert result["status"] == "monitor_only"
        assert result["critical_zones"].empty


def _ejscreen_gdf_for(grid):
    import geopandas as gpd
    return gpd.GeoDataFrame(
        {"ID": ["T1"], "ACSTOTPOP": [5000], "P_DEMOGIDX_5": [90.0],
         "PEOPCOLORPCT": [70.0], "OVER64PCT": [12.0], "UNDER5PCT": [8.0]},
        geometry=[grid.union_all()], crs="EPSG:4326",
    )
