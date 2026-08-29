"""
GridHeat AI - LangGraph agentic workflow, Texas pilot (was notebook
Section 7).

HeatAgent -> DemandForecastAgent -> GridAssetAgent -> OutageAgent ->
VulnerabilityAgent -> RiskEngine -> (ScenarioGenerator | Monitor)

Same graph shape and inlining strategy as the California version (a
LangGraph node function often gets shipped/executed in isolation - e.g. by
LangGraph Studio, or a worker process - so imports that only exist as a
notebook cell name are avoided; see backend/risk_engine.py and
backend/optimization.py for the equivalent standalone modules used
elsewhere).

What's different for Texas:
- OutageAgent no longer does a real spatial join - EAGLE-I has no
  per-event geometry, so it just scores the same broadcast county-level
  total every other cell uses against outage_reference_range.
- DemandForecastAgent's state["demand_model"] is a bundle dict
  ({"linear", "multivariate", "features"}), not a bare estimator -
  predict_demand_stress() prefers the multivariate model whenever its live
  features are fetchable this run, falling back to the univariate
  (temp-only) model otherwise.
- RiskEngine gets an optional infra_weights table to spatially redistribute
  the single system-wide demand_score across zones (backend/risk_engine.py).

LangSmith tracing (optional) is wired up at import time below, right after
the imports - see LANGCHAIN_API_KEY in backend/config.py / .env.example.
"""
from datetime import date, datetime, timedelta
from typing import TypedDict
import os

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape
from langgraph.graph import StateGraph, START, END

from backend import data_access
from backend.config import (
    RISK_TABLE_PATH, LIVE_HEAT_PATH, DEFAULT_RISK_THRESHOLD, LANGCHAIN_API_KEY,
    PILOT_CRS, EIA_API_KEY,
)
from backend.risk_engine import build_risk_table, score_against_reference_range


# ============ LangSmith tracing (optional, purely additive) ============
if LANGCHAIN_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
    os.environ.setdefault("LANGCHAIN_PROJECT", "GridHeat-AI-Texas")


class GridHeatState(TypedDict, total=False):
    risk_threshold: float
    target_date: str | None
    fg_client: object
    pilot_aoi: dict
    grid: object
    demand_model: object
    baseline_demand_mw: float
    demand_historical_range: tuple
    outage_reference_range: tuple
    pilot_total_outage_customers: float
    pilot_county: str
    infra_weights: pd.DataFrame  # from Section 1.3c - optional, enables demand spatial redistribution
    force_refresh_heat: bool

    live_heat: pd.DataFrame
    demand_stress_pct: float
    demand_score: float
    demand_model_used: str  # "multivariate" or "linear (fallback)"
    outage_score: float
    lines_joined: pd.DataFrame
    vulnerability_joined: pd.DataFrame
    risk_table: pd.DataFrame
    critical_zones: pd.DataFrame
    status: str


# ============ Shared join primitives ============

def join_lines(grid, lines_gdf, id_col="OBJECTID"):
    lines_gdf = lines_gdf.to_crs(grid.crs)
    joined = gpd.sjoin(grid, lines_gdf, how="inner", predicate="intersects")
    return joined[["zone_id", id_col]].drop_duplicates().reset_index(drop=True)


def join_polygons_area_weighted(grid, polygons_gdf, id_col, extensive_cols=None, intensive_cols=None):
    """extensive_cols (counts, e.g. population): apportioned by the source
    polygon's area fraction. intensive_cols (scores/rates): area-weighted
    AVERAGE within each cell (not diluted by how much of the source
    polygon's total area landed there)."""
    polygons_gdf = polygons_gdf.to_crs(grid.crs)
    extensive_cols = extensive_cols or []
    intensive_cols = intensive_cols or []
    grid_m = grid.to_crs(PILOT_CRS)   # Texas Centric Albers Equal Area
    polys_m = polygons_gdf.to_crs(PILOT_CRS)
    overlay = gpd.overlay(grid_m, polys_m, how="intersection")
    overlay["piece_area"] = overlay.geometry.area

    results = []
    if extensive_cols:
        poly_total_area = polys_m.set_index(id_col).geometry.area
        overlay["poly_total_area"] = overlay[id_col].map(poly_total_area)
        overlay["area_fraction_of_source"] = overlay["piece_area"] / overlay["poly_total_area"]
        ext = overlay.copy()
        for col in extensive_cols:
            ext[col] = ext[col] * ext["area_fraction_of_source"]
        results.append(ext.groupby("zone_id")[extensive_cols].sum())
    if intensive_cols:
        cell_covered_area = overlay.groupby("zone_id")["piece_area"].transform("sum")
        overlay["area_fraction_of_cell"] = overlay["piece_area"] / cell_covered_area
        intens = overlay.copy()
        for col in intensive_cols:
            intens[col] = intens[col] * intens["area_fraction_of_cell"]
        results.append(intens.groupby("zone_id")[intensive_cols].sum())
    if not results:
        raise ValueError("Must supply at least one of extensive_cols or intensive_cols")
    return pd.concat(results, axis=1).reset_index()


def tiles_to_geodataframe(map_data: dict) -> gpd.GeoDataFrame:
    rows = []
    for i, feature in enumerate(map_data["features"]):
        props = feature["properties"]
        geom = shape(feature["geometry"])
        rows.append({**props, "tile_id": i, "geometry": geom})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def fetch_live_heat_by_zone(client, polygon_aoi: dict, grid: gpd.GeoDataFrame, target_date: str | None = None) -> pd.DataFrame:
    """FortyGuard heatmaps summarize a completed day, not an instantaneous
    reading - 'live' means 'most recent day with data' (defaults to yesterday)."""
    if target_date is None:
        target_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    response = client.create_heatmap(polygon_aoi=polygon_aoi, start_date=target_date, filter_type=3, granularity=100)
    tiles_gdf = tiles_to_geodataframe(response["result"]["map_data"])

    heat_by_zone = join_polygons_area_weighted(grid, tiles_gdf, id_col="tile_id", intensive_cols=["average_temperature"])
    heat_by_zone = heat_by_zone.rename(columns={"average_temperature": "heat_raw_c"})
    heat_by_zone["heat_raw_f"] = heat_by_zone["heat_raw_c"] * 9 / 5 + 32
    heat_by_zone["as_of_date"] = target_date
    return heat_by_zone


def fetch_recent_ercot_demand(end_date, n_days: int = 3):
    """Fetch up to n_days of actual ERCOT system demand (EIA-930, ERCO
    respondent) ending the day before end_date. Returns a list of daily peak
    MW values, oldest first (may be shorter than n_days on partial failure -
    e.g. EIA-930's typical 1-2 day publication lag). Returns [] (not a
    raise) if EIA_API_KEY isn't configured - the multivariate model's
    fallback to "linear" in predict_demand_stress handles that gracefully."""
    if not EIA_API_KEY:
        return []
    try:
        start = (end_date - timedelta(days=n_days)).strftime("%Y-%m-%d")
        end = (end_date - timedelta(days=1)).strftime("%Y-%m-%d")
        resp = requests.get(
            "https://api.eia.gov/v2/electricity/rto/region-data/data/",
            params={"api_key": EIA_API_KEY, "frequency": "hourly", "data[0]": "value",
                    "facets[respondent][]": "ERCO", "facets[type][]": "D",
                    "start": f"{start}T00", "end": f"{end}T23",
                    "sort[0][column]": "period", "sort[0][direction]": "asc", "length": 5000},
            timeout=30)
        resp.raise_for_status()
        data = resp.json()["response"]["data"]
        if not data:
            return []
        df = pd.DataFrame(data)
        df["period"] = pd.to_datetime(df["period"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"] = df["period"].dt.date
        return df.groupby("date")["value"].max().sort_index().tolist()
    except Exception as e:
        print(f"    [prev-day ERCOT demand] unavailable ({e})")
        return []


def fetch_live_solar_irradiance(fg_client, pilot_aoi, as_of_date, temperature_c: float, hour: int = 15):
    """environmental_parameters() requires `temperature` (Celsius) as input."""
    try:
        centroid = shape(pilot_aoi["features"][0]["geometry"]).centroid
        resp = fg_client.environmental_parameters(
            latitude=centroid.y, longitude=centroid.x, temperature=temperature_c,
            start_date=as_of_date.strftime("%Y-%m-%d"), start_time=f"{hour:02d}:00",
            filter_type=1,
        )
        locations = resp["result"].get("locations") or []
        if not locations:
            return None
        params = locations[0].get("parameters", {})
        for key in ("solar_irradiance_wm2", "solar_irradiance", "irradiance_wm2", "ghi_wm2", "ghi", "solar"):
            if key in params:
                return params[key]
        clear_sky = locations[0].get("solar_irradiance", {}).get("clear_sky", {})
        return clear_sky.get("ghi")
    except Exception as e:
        print(f"    [solar] unavailable ({e})")
        return None


def predict_demand_stress(demand_bundle: dict, baseline_mw: float, current_temp_f: float,
                           fg_client, pilot_aoi: dict, as_of_date=None):
    """Returns (predicted_mw, demand_stress_pct, model_used). Prefers
    demand_bundle["multivariate"]; falls back to demand_bundle["linear"]
    (avg_temp_f only) whenever a required live feature isn't fetchable -
    EIA-930's publication lag, a FortyGuard quota miss, etc. NOTE: costs
    extra API calls (EIA-930 for rolling/previous-day demand, FortyGuard
    heatmap for previous-day temp, FortyGuard env_params for solar) - call
    once per pipeline run, not in a loop."""
    as_of_date = as_of_date or (datetime.now() - timedelta(days=1))
    features = demand_bundle.get("features")

    if demand_bundle.get("multivariate") is not None and features:
        row = {
            "avg_temp_f": current_temp_f,
            "dow": as_of_date.weekday(),
            "is_weekend": int(as_of_date.weekday() >= 5),
            "month": as_of_date.month,
        }
        recent = fetch_recent_ercot_demand(as_of_date, n_days=3)
        if recent:
            row["prev_day_demand_mw"] = recent[-1]
            row["rolling_3d_demand_mw"] = sum(recent) / len(recent)

        try:
            prev_resp = fg_client.create_heatmap(
                polygon_aoi=pilot_aoi, start_date=(as_of_date - timedelta(days=1)).strftime("%Y-%m-%d"),
                filter_type=3, granularity=100)
            row["prev_temp_f"] = prev_resp["result"]["stats_data"]["temperature_stats"]["mean"] * 9 / 5 + 32
        except Exception as e:
            print(f"    [prev-day temp] unavailable ({e})")

        try:
            import holidays as holidays_lib
            row["is_holiday"] = int(as_of_date.date() in holidays_lib.US(years=[as_of_date.year]))
        except ImportError:
            row["is_holiday"] = int((as_of_date.month, as_of_date.day) in {(7, 4), (1, 1), (12, 25)})

        if "solar_irradiance_wm2" in features:
            current_temp_c = (current_temp_f - 32) * 5 / 9
            row["solar_irradiance_wm2"] = fetch_live_solar_irradiance(
                fg_client, pilot_aoi, as_of_date, temperature_c=current_temp_c)

        if all(row.get(f) is not None for f in features):
            X_live = pd.DataFrame([row])[features]
            pred = demand_bundle["multivariate"].predict(X_live)[0]
            stress = (pred - baseline_mw) / baseline_mw * 100
            return pred, stress, "multivariate"
        missing = [f for f in features if row.get(f) is None]
        print(f"    [predict_demand_stress] missing live features {missing} - falling back to univariate model")

    pred = demand_bundle["linear"].predict(pd.DataFrame({"avg_temp_f": [current_temp_f]}))[0]
    stress = (pred - baseline_mw) / baseline_mw * 100
    return pred, stress, "linear (fallback)"


# ============ Agent nodes ============

def heat_agent(state: GridHeatState) -> GridHeatState:
    """Reuses LIVE_HEAT_PATH's cache if it already has today's target date,
    instead of always calling FortyGuard."""
    target_date = state.get("target_date")
    if target_date is None:
        target_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    if LIVE_HEAT_PATH.exists() and not state.get("force_refresh_heat", False):
        cached = pd.read_csv(LIVE_HEAT_PATH)
        if not cached.empty and str(cached["as_of_date"].iloc[0]) == target_date:
            return {"live_heat": cached}

    live_heat = fetch_live_heat_by_zone(
        client=state["fg_client"], polygon_aoi=state["pilot_aoi"],
        grid=state["grid"], target_date=target_date,
    )
    return {"live_heat": live_heat}


def demand_forecast_agent(state: GridHeatState) -> GridHeatState:
    """state["demand_model"] is a bundle dict ({"linear", "multivariate",
    "features"} - see notebook Section 4-FINAL), not a bare sklearn
    estimator. predict_demand_stress() picks whichever model it can
    actually feed with live data this run."""
    demand_bundle = state["demand_model"]
    baseline_mw = state["baseline_demand_mw"]
    current_temp_f = state["live_heat"]["heat_raw_f"].mean()
    predicted_mw, demand_stress_pct, model_used = predict_demand_stress(
        demand_bundle, baseline_mw, current_temp_f,
        fg_client=state["fg_client"], pilot_aoi=state["pilot_aoi"], as_of_date=None)
    demand_score = score_against_reference_range(demand_stress_pct, state["demand_historical_range"])
    return {"demand_stress_pct": demand_stress_pct, "demand_score": demand_score, "demand_model_used": model_used}


def grid_asset_agent(state: GridHeatState) -> GridHeatState:
    lines_gdf = data_access.load_transmission_lines()
    return {"lines_joined": join_lines(state["grid"], lines_gdf, id_col="OBJECTID")}


def outage_agent(state: GridHeatState) -> GridHeatState:
    """EAGLE-I has no per-event geometry (unlike PSPS) - re-reads the same
    county-level total every other cell uses and scores it against the
    cross-county reference range from notebook Section 2's Stage B, rather
    than doing a spatial join that has nothing to differentiate."""
    outage_score = score_against_reference_range(
        state["pilot_total_outage_customers"], state["outage_reference_range"]
    )
    return {"outage_score": outage_score}


def vulnerability_agent(state: GridHeatState) -> GridHeatState:
    ej_gdf = data_access.load_ejscreen()
    vulnerability_joined = join_polygons_area_weighted(
        state["grid"], ej_gdf, id_col="ID",
        extensive_cols=["ACSTOTPOP"],
        intensive_cols=["P_DEMOGIDX_5", "PEOPCOLORPCT", "OVER64PCT", "UNDER5PCT"],
    )
    return {"vulnerability_joined": vulnerability_joined}


def risk_engine_node(state: GridHeatState) -> GridHeatState:
    risk_table = build_risk_table(
        grid=state["grid"], live_heat=state["live_heat"],
        vulnerability_joined=state["vulnerability_joined"], lines_joined=state["lines_joined"],
        demand_score=state["demand_score"], outage_score=state["outage_score"],
        infra_weights=state.get("infra_weights"),
    )
    return {"risk_table": risk_table}


def route_by_risk(state: GridHeatState) -> str:
    threshold = state["risk_threshold"]
    critical = state["risk_table"][state["risk_table"]["grid_heat_risk"] >= threshold]
    return "monitor_only" if critical.empty else "escalated"


def scenario_generator_node(state: GridHeatState) -> GridHeatState:
    critical_zones = state["risk_table"][state["risk_table"]["grid_heat_risk"] >= state["risk_threshold"]].copy()
    return {"critical_zones": critical_zones, "status": "escalated"}


def monitor_node(state: GridHeatState) -> GridHeatState:
    return {"status": "monitor_only", "critical_zones": pd.DataFrame(columns=["zone_id", "grid_heat_risk"])}


def build_graph():
    graph = StateGraph(GridHeatState)
    graph.add_node("HeatAgent", heat_agent)
    graph.add_node("DemandForecastAgent", demand_forecast_agent)
    graph.add_node("GridAssetAgent", grid_asset_agent)
    graph.add_node("OutageAgent", outage_agent)
    graph.add_node("VulnerabilityAgent", vulnerability_agent)
    graph.add_node("RiskEngine", risk_engine_node)
    graph.add_node("ScenarioGenerator", scenario_generator_node)
    graph.add_node("Monitor", monitor_node)

    graph.add_edge(START, "HeatAgent")
    graph.add_edge("HeatAgent", "DemandForecastAgent")
    graph.add_edge("DemandForecastAgent", "GridAssetAgent")
    graph.add_edge("GridAssetAgent", "OutageAgent")
    graph.add_edge("OutageAgent", "VulnerabilityAgent")
    graph.add_edge("VulnerabilityAgent", "RiskEngine")
    graph.add_conditional_edges("RiskEngine", route_by_risk, {"escalated": "ScenarioGenerator", "monitor_only": "Monitor"})
    graph.add_edge("ScenarioGenerator", END)
    graph.add_edge("Monitor", END)
    return graph.compile()


def run_pipeline(fg_client, target_date: str | None = None, risk_threshold: float = DEFAULT_RISK_THRESHOLD,
                  save_results: bool = True) -> dict:
    """Convenience wrapper: wires real state from data_access + config and
    invokes the graph. This is what frontend/app.py and integration tests
    call - unit tests instead exercise individual node functions with mocks
    (see tests/test_graph.py)."""
    from backend.config import PILOT_COUNTY

    grid = data_access.load_grid()
    pilot_aoi = data_access.load_pilot_aoi()
    demand_model = data_access.load_demand_model()
    baseline_demand_mw, demand_historical_range = data_access.load_baseline_and_stress_range()
    pilot_total_outage_customers = data_access.load_pilot_total_outage_customers()
    outage_reference_range = data_access.load_outage_reference_range()
    infra_weights = data_access.load_infra_weights()

    app = build_graph()
    initial_state: GridHeatState = {
        "risk_threshold": risk_threshold,
        "target_date": target_date,
        "fg_client": fg_client,
        "pilot_aoi": pilot_aoi,
        "grid": grid,
        "demand_model": demand_model,
        "baseline_demand_mw": baseline_demand_mw,
        "demand_historical_range": demand_historical_range,
        "outage_reference_range": outage_reference_range,
        "pilot_total_outage_customers": pilot_total_outage_customers,
        "pilot_county": PILOT_COUNTY,
        "infra_weights": infra_weights,
    }
    result = app.invoke(initial_state)

    if save_results:
        result["risk_table"].to_csv(RISK_TABLE_PATH, index=False)
        result["live_heat"].to_csv(LIVE_HEAT_PATH, index=False)

    return result
