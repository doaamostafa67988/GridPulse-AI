"""
FastAPI thin layer over backend/ (graph.py, risk_engine.py, optimization.py,
llm_explain.py) - exposes the same data the Streamlit frontend (frontend/app.py)
reads directly, as JSON, for the Next.js frontend (web/) to consume.

No calculation logic lives here - every endpoint just calls into the existing
backend modules and serializes the result. If backend/data_access.py can't
find the real artifact files in data/ (see backend/config.py), this module
falls back to backend/mock_data.py automatically, so the API - and the
frontend behind it - works with zero setup (no data pipeline run, no
FORTYGUARD_API_KEY/GROQ_API_KEY). Swap in real data by populating data/ per
config.py; nothing here needs to change.

Run from the repo root:

    uvicorn backend.api:app --reload --port 8000

CORS is wide open (allow_origins=["*"]) since this is a local/demo backend
behind no auth - tighten this before any real deployment.
"""
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend import data_access, mock_data
from backend.config import ACTIONS, DEFAULT_RISK_THRESHOLD
from backend.llm_explain import build_zone_evidence, explain_plan, explain_zone, get_groq_client
from backend.optimization import build_candidate_options, optimize_plan, summarize_plan

app = FastAPI(title="GridHeat AI API - Texas Pilot")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


# ============ Data loading (real data if present, else mock) ============

def _using_mock() -> bool:
    from backend.config import RISK_TABLE_PATH
    return not RISK_TABLE_PATH.exists()


def _load_risk_table() -> pd.DataFrame:
    if _using_mock():
        table = mock_data.mock_risk_table()
    else:
        table = data_access.load_risk_table()
    return _add_heat_raw_f(table)


def _sanitize_heat_raw_f(risk_table: pd.DataFrame) -> pd.DataFrame:
    """A merged/renamed heat_raw_f column can contain NaN (e.g. a zone_id
    with no match in tx_live_heat_by_zone.csv). pandas keeps NaN as a
    float, and Python's json module (which FastAPI/Starlette use here)
    serializes float NaN as the bare token `NaN` - valid in JS source but
    not valid JSON, so the frontend's response.json() throws and the
    *entire* response fails to parse, not just that one zone. Swap NaN for
    None so it serializes as JSON `null` instead, which Optional[float]
    handles fine."""
    risk_table = risk_table.copy()
    risk_table["heat_raw_f"] = risk_table["heat_raw_f"].apply(
        lambda v: None if pd.isna(v) else float(v)
    )
    return risk_table


def _add_heat_raw_f(risk_table: pd.DataFrame) -> pd.DataFrame:
    """risk_engine.py's build_risk_table names the actual-temperature
    column "heat_raw" (already in °F - see graph.py's heat_raw_f -> heat_raw
    rename during the merge). Expose it to the API as "heat_raw_f" so it
    reads unambiguously as Fahrenheit on the frontend, without touching the
    internal column name risk_engine.py/notebooks already write to disk.

    Some already-saved data/tx_risk_table.csv files predate this column
    being carried through to the risk table itself. graph.py's heat_agent
    node saves a separate tx_live_heat_by_zone.csv on every pipeline
    run though (zone_id -> heat_raw_c/heat_raw_f), so merge from there
    before giving up - this recovers the real temperature without needing
    to re-run the notebook pipeline, as long as that file exists from a
    previous run."""
    if "heat_raw" in risk_table.columns:
        return _sanitize_heat_raw_f(risk_table.rename(columns={"heat_raw": "heat_raw_f"}))
    if "heat_raw_f" in risk_table.columns:
        return _sanitize_heat_raw_f(risk_table)

    live_heat = data_access.load_live_heat()
    if not live_heat.empty and "heat_raw_f" in live_heat.columns:
        merged = risk_table.merge(live_heat[["zone_id", "heat_raw_f"]], on="zone_id", how="left")
        return _sanitize_heat_raw_f(merged)

    print(
        "[api] warning: no 'heat_raw'/'heat_raw_f' in the risk table, and no "
        "data/tx_live_heat_by_zone.csv to merge it from either - actual "
        "temperature (°F) won't be shown on the frontend. Risk table columns: "
        f"{list(risk_table.columns)}. Re-run the notebook pipeline to regenerate both files."
    )
    risk_table = risk_table.copy()
    risk_table["heat_raw_f"] = None
    return risk_table


def _load_grid_geojson() -> dict:
    if _using_mock():
        return mock_data.mock_grid_geojson()
    return _rewind_geojson(data_access.load_grid().to_crs("EPSG:4326").__geo_interface__)


def _rewind_geojson(fc: dict) -> dict:
    """Force every polygon ring to RFC 7946 winding (exterior ring
    counter-clockwise, holes clockwise) before handing GeoJSON to the
    frontend.

    gpd.GeoDataFrame.__geo_interface__ passes through whatever ring
    orientation the source file had - shapely/GeoPandas don't normalize
    it. Many US government GIS shapefiles (the kind this project's real
    grid/transmission artifacts are built from) are digitized with
    clockwise exterior rings, which violates RFC 7946 but many tools
    tolerate anyway. MapLibre GL's client-side polygon triangulator can
    silently produce degenerate (zero-area) triangles for incorrectly-
    wound rings on some geometries - the source loads without error, the
    layer "exists", but nothing actually paints. Rewinding here fixes it
    at the source instead of asking every consumer of this endpoint to
    work around it.
    """
    from shapely.geometry import mapping, shape
    from shapely.geometry.polygon import orient

    for feature in fc.get("features", []):
        geom = feature.get("geometry")
        if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        feature["geometry"] = mapping(orient(shape(geom), sign=1.0))
    return fc


def _load_lines_geojson() -> dict:
    if _using_mock():
        return mock_data.mock_transmission_lines_geojson()
    return data_access.load_transmission_lines().to_crs("EPSG:4326").__geo_interface__


def _load_battery_joined() -> pd.DataFrame:
    if _using_mock():
        return mock_data.mock_battery_joined()
    return data_access.load_battery_joined()


def _load_lines_joined() -> pd.DataFrame:
    if _using_mock():
        return mock_data.mock_lines_joined()
    return data_access.load_lines_joined()


def _critical_zones(risk_table: pd.DataFrame, threshold: float) -> pd.DataFrame:
    return risk_table[risk_table["grid_heat_risk"] >= threshold].copy()


_groq_client = None
_groq_client_loaded = False


def _get_groq_client_cached():
    global _groq_client, _groq_client_loaded
    if not _groq_client_loaded:
        _groq_client = get_groq_client()
        _groq_client_loaded = True
    return _groq_client


# ============ Response models ============

class MetaResponse(BaseModel):
    using_mock_data: bool
    n_zones: int
    n_critical_zones: int
    risk_threshold: float
    llm_configured: bool


class ZoneRisk(BaseModel):
    zone_id: str
    grid_heat_risk: float
    heat_score: float
    demand_score: float
    infra_score: float
    outage_score: float
    vuln_score: float
    # Actual temperature in °F (risk_engine.py's "heat_raw" column) - the
    # other *_score fields are all normalized 0-100 for the risk formula,
    # this is the only field that's a real physical unit. Optional because
    # an older cached tx_risk_table.csv (generated before this field
    # existed) won't have the column; _add_heat_raw_f below fills it with
    # None in that case rather than failing response validation.
    heat_raw_f: Optional[float] = None


class PlanAction(BaseModel):
    zone_id: str
    action: str
    cost: int
    value: float


class PlanResponse(BaseModel):
    budget: int
    total_cost: int
    total_value: float
    actions: list[PlanAction]
    action_catalog: dict


class ExplainZoneResponse(BaseModel):
    zone_id: str
    explanation: str


class ExplainPlanRequest(BaseModel):
    budget: int = 50_000


class ExplainPlanResponse(BaseModel):
    explanation: str
    total_cost: int
    total_value: float
    budget: int


# ============ Endpoints ============

@app.get("/api/meta", response_model=MetaResponse)
def get_meta():
    risk_table = _load_risk_table()
    critical = _critical_zones(risk_table, DEFAULT_RISK_THRESHOLD)
    return MetaResponse(
        using_mock_data=_using_mock(),
        n_zones=len(risk_table),
        n_critical_zones=len(critical),
        risk_threshold=DEFAULT_RISK_THRESHOLD,
        llm_configured=_get_groq_client_cached() is not None,
    )


@app.get("/api/risk-table", response_model=list[ZoneRisk])
def get_risk_table():
    risk_table = _load_risk_table()
    return risk_table.to_dict(orient="records")


@app.get("/api/critical-zones", response_model=list[ZoneRisk])
def get_critical_zones(threshold: Optional[float] = None):
    risk_table = _load_risk_table()
    t = threshold if threshold is not None else DEFAULT_RISK_THRESHOLD
    return _critical_zones(risk_table, t).to_dict(orient="records")


@app.get("/api/map")
def get_map_data():
    """Grid cells and transmission lines as GeoJSON, plus the risk table, so
    the frontend can render its own map (e.g. via MapLibre/Deck.gl) without
    depending on the Streamlit/folium HTML embed."""
    risk_table = _load_risk_table()
    grid_geojson = _load_grid_geojson()
    lines_geojson = _load_lines_geojson()

    risk_by_zone = {
        row["zone_id"]: (row["grid_heat_risk"], row.get("heat_raw_f"))
        for row in risk_table.to_dict(orient="records")
    }
    for feature in grid_geojson.get("features", []):
        zone_id = feature["properties"].get("zone_id")
        risk, heat_raw_f = risk_by_zone.get(zone_id, (None, None))
        feature["properties"]["grid_heat_risk"] = risk
        feature["properties"]["heat_raw_f"] = heat_raw_f

    return {"grid": grid_geojson, "lines": lines_geojson}


@app.get("/api/plan", response_model=PlanResponse)
def get_plan(budget: int = 50_000):
    if budget < 0:
        raise HTTPException(status_code=400, detail="budget must be >= 0")

    risk_table = _load_risk_table()
    critical_zones = _critical_zones(risk_table, DEFAULT_RISK_THRESHOLD)
    battery_joined = _load_battery_joined()

    options = build_candidate_options(critical_zones, battery_joined)
    result = optimize_plan(options, budget)
    plan_df = summarize_plan(result)

    return PlanResponse(
        budget=budget, total_cost=result["total_cost"], total_value=round(result["total_value"], 2),
        actions=plan_df.to_dict(orient="records"), action_catalog=ACTIONS,
    )


@app.get("/api/explain/zone/{zone_id}", response_model=ExplainZoneResponse)
def get_explain_zone(zone_id: str):
    risk_table = _load_risk_table()
    if zone_id not in set(risk_table["zone_id"]):
        raise HTTPException(status_code=404, detail=f"zone_id '{zone_id}' not found")

    lines_joined = _load_lines_joined()
    battery_joined = _load_battery_joined()
    evidence = build_zone_evidence(zone_id, risk_table, lines_joined, battery_joined)

    client = _get_groq_client_cached()
    explanation = explain_zone(client, evidence)
    return ExplainZoneResponse(zone_id=zone_id, explanation=explanation)


@app.post("/api/explain/plan", response_model=ExplainPlanResponse)
def post_explain_plan(body: ExplainPlanRequest):
    if body.budget < 0:
        raise HTTPException(status_code=400, detail="budget must be >= 0")

    risk_table = _load_risk_table()
    critical_zones = _critical_zones(risk_table, DEFAULT_RISK_THRESHOLD)
    battery_joined = _load_battery_joined()

    options = build_candidate_options(critical_zones, battery_joined)
    result = optimize_plan(options, body.budget)
    plan_df = summarize_plan(result)

    client = _get_groq_client_cached()
    if plan_df.empty:
        explanation = "No actions were selected within this budget, so there's no plan to explain."
    else:
        explanation = explain_plan(client, plan_df, result["total_cost"], result["total_value"], body.budget)

    return ExplainPlanResponse(
        explanation=explanation, total_cost=result["total_cost"],
        total_value=round(result["total_value"], 2), budget=body.budget,
    )
