"""
Loads the static artifact files produced by
notebooks/GridHeat_AI_Pipeline_Texas.ipynb (the one-time data pipeline).
Both the frontend and the LangGraph nodes in graph.py read through these
functions rather than hardcoding file paths directly, so there's exactly
one place to change if the data layout moves.

Texas-specific notes (see backend/config.py and the notebook for the full
rationale):
- No PSPS-equivalent per-event outage geometry exists for Texas (EAGLE-I is
  county-level only) - load_eagle_i_outages / load_outage_reference_range
  replace load_psps/load_psps_joined from the California version.
- CalEnviroScreen is replaced by EPA EJScreen (load_ejscreen /
  load_vulnerability_joined, keyed on P_DEMOGIDX_5 rather than CIscore).
- An extra load_infra_weights() has no California equivalent - it feeds the
  infra-density spatial redistribution of the single ERCOT-wide demand
  score (see backend/risk_engine.py).
"""
import geopandas as gpd
import joblib
import pandas as pd

from backend import config


def load_grid() -> gpd.GeoDataFrame:
    return gpd.read_file(config.HEAT_ZONE_GRID_PATH)


def load_transmission_lines() -> gpd.GeoDataFrame:
    return gpd.read_file(config.TRANSMISSION_LINES_PATH)


def load_substations() -> gpd.GeoDataFrame:
    return gpd.read_file(config.SUBSTATIONS_PATH)


def load_ejscreen() -> gpd.GeoDataFrame:
    return gpd.read_file(config.EJSCREEN_PATH)


def load_lines_joined() -> pd.DataFrame:
    return pd.read_csv(config.LINES_JOINED_PATH)


def load_vulnerability_joined() -> pd.DataFrame:
    return pd.read_csv(config.VULNERABILITY_JOINED_PATH)


def load_battery_joined() -> pd.DataFrame:
    if config.BATTERY_JOINED_PATH.exists():
        return pd.read_csv(config.BATTERY_JOINED_PATH)
    return pd.DataFrame(columns=["zone_id", "n_battery_sites"])


def load_infra_weights() -> pd.DataFrame:
    """zone_id -> infra_weight (sums to 1.0 across the AOI) - see notebook
    Section 1.3c / backend/risk_engine.py's apply_infra_reweighting. Absent
    is a valid state (falls back to a flat broadcast of demand_score across
    every zone), not an error - EIA-861 utility-sales weighting doesn't
    apply in ERCOT's deregulated market, so this proxy is best-effort."""
    if config.INFRA_WEIGHTS_PATH.exists():
        return pd.read_csv(config.INFRA_WEIGHTS_PATH)
    return pd.DataFrame(columns=["zone_id", "n_substations", "n_transmission_lines", "infra_weight"])


def load_demand_model():
    """Returns the bundle dict {"linear", "multivariate", "features"} saved
    by notebook Section 4-FINAL, NOT a bare sklearn estimator - see
    backend/graph.py's predict_demand_stress for how the two are chosen
    between at run time."""
    return joblib.load(config.DEMAND_MODEL_PATH)


def load_temp_demand_merged() -> pd.DataFrame:
    return pd.read_csv(config.TEMP_DEMAND_MERGED_PATH)


def load_baseline_and_stress_range() -> tuple[float, tuple[float, float]]:
    """Returns (baseline_demand_mw, (min_stress_pct, max_stress_pct)) computed
    from the historical temp/demand data - used to score demand_stress_pct
    against a real reference range (see risk_engine.score_against_reference_range)."""
    merged = load_temp_demand_merged()
    baseline_demand_mw = merged["demand_peak_mw"].mean()
    stress_pct = (merged["demand_peak_mw"] - baseline_demand_mw) / baseline_demand_mw * 100
    return baseline_demand_mw, (stress_pct.min(), stress_pct.max())


def load_pilot_aoi() -> dict:
    import json
    with open(config.PILOT_AOI_PATH) as f:
        return json.load(f)


def load_eagle_i_outages() -> pd.DataFrame:
    """DOE/ORNL EAGLE-I county-level, 15-minute outage readings, already
    filtered to Texas summer months (June-September) - see notebook
    Section 1.2. County-level only: no per-event geometry, unlike CPUC's
    PSPS data, hence no spatial join anywhere downstream of this."""
    return pd.read_csv(config.EAGLE_I_OUTAGES_PATH, parse_dates=["run_start_time"])


def load_pilot_total_outage_customers(customers_col: str = "sum") -> float:
    """Cumulative customers-out for PILOT_COUNTY over the loaded EAGLE-I
    window - the single county-level number broadcast to every zone by
    backend/graph.py's outage_agent (see backend/risk_engine.py)."""
    df = load_eagle_i_outages()
    col = customers_col if customers_col in df.columns else (
        "customers_out" if "customers_out" in df.columns else "sum"
    )
    county_col = "county" if "county" in df.columns else "county_name"
    mask = df[county_col].astype(str).str.strip().str.lower() == config.PILOT_COUNTY.strip().lower()
    return float(df.loc[mask, col].sum())


def load_outage_reference_range() -> tuple[float, float]:
    """The (min, max) cumulative summer customers-out total across the
    candidate counties considered in notebook Section 2's Stage B - the
    real "low vs high" scale a single county-level number is scored
    against (score_against_reference_range in backend/risk_engine.py).
    Falls back to (0.0, pilot_total) if the scoreboard artifact isn't
    present, which degrades outage_score to 100 whenever there's any
    outage history at all - clearly documented rather than silently wrong."""
    if config.COUNTY_SCOREBOARD_PATH.exists():
        scoreboard = pd.read_csv(config.COUNTY_SCOREBOARD_PATH)
        return float(scoreboard["outages"].min()), float(scoreboard["outages"].max())
    pilot_total = load_pilot_total_outage_customers()
    return 0.0, max(pilot_total, 1.0)


def load_risk_table() -> pd.DataFrame:
    """The most recent computed risk table, if one has been saved (e.g. by a
    previous graph run). Raises if none exists yet - callers should run the
    graph first (see graph.run_pipeline) rather than silently getting stale
    or absent data."""
    if not config.RISK_TABLE_PATH.exists():
        raise FileNotFoundError(
            f"{config.RISK_TABLE_PATH} not found - run backend.graph.run_pipeline() "
            f"at least once to generate it."
        )
    return pd.read_csv(config.RISK_TABLE_PATH)


def load_live_heat() -> pd.DataFrame:
    """zone_id -> heat_raw_c/heat_raw_f (actual temperature), saved by
    graph.py's heat_agent node as a side artifact of the same pipeline run
    that produces the risk table. Returns empty (not a raise) if it doesn't
    exist, since callers treat a missing temperature as optional, not fatal."""
    if config.LIVE_HEAT_PATH.exists():
        return pd.read_csv(config.LIVE_HEAT_PATH)
    return pd.DataFrame(columns=["zone_id", "heat_raw_c", "heat_raw_f"])
