"""
Deterministic Grid Heat Risk Engine - was notebook Section 6 (Texas pilot).
No LLM involved anywhere in here; fixed formulas only.

Same five-component design as the California version - heat (30%), demand
stress (25%), infrastructure density (20%), historical outage exposure
(15%), vulnerability (10%) - min-max normalized to 0-100 before weighting.

Two things are genuinely different for Texas (see the notebook's Section 6
markdown for the full rationale):

1. demand_score and outage_score are each a SINGLE system/county-level
   number (EIA-930 has no zone breakdown; EAGLE-I has no per-event
   geometry), scored against a real historical/comparative reference range
   via score_against_reference_range - NOT normalize_0_100 across zones,
   which would always give 0 since every zone starts out identical.
2. demand_score is then spatially redistributed across zones proportional
   to each zone's share of built infrastructure (apply_infra_reweighting),
   rather than broadcast identically everywhere - a proxy layered on a
   proxy, stated explicitly rather than silently smoothed over.
   outage_score is NOT reweighted this way (infra density has no
   established relationship to outage history the way it plausibly does to
   load) - it stays a flat broadcast value.
"""
import numpy as np
import pandas as pd

from backend.config import RISK_WEIGHTS


def normalize_0_100(series: pd.Series) -> pd.Series:
    """Min-max normalize to 0-100. A constant column (no variation across
    zones) is set to 0 for every zone rather than dividing by zero - 'no
    variation' should not count as risk. Used for components that
    genuinely vary across zones (heat, infrastructure, vulnerability)."""
    lo, hi = series.min(), series.max()
    if hi - lo == 0:
        return pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo) * 100.0


def score_against_reference_range(value: float, reference_range: tuple) -> float:
    """For components that are a single number broadcast to every zone by
    construction (demand_stress_pct pre-reweighting, and Texas's
    county-level outage total) - score against a real historical/
    comparative reference range instead of min-max across zones, which
    always gives 0 when every zone has the identical value."""
    lo, hi = reference_range
    if hi - lo == 0:
        return 0.0
    return float(np.clip((value - lo) / (hi - lo) * 100.0, 0, 100))


def apply_infra_reweighting(risk: pd.DataFrame, base_score: float, infra_weights: pd.DataFrame) -> pd.Series:
    """Redistribute a single broadcast score across zones proportionally to
    infra_weight (which sums to 1.0 across the AOI's zones). The multiplier
    is infra_weight * n_zones, so its average across zones is exactly 1.0 -
    meaning the AOI-wide average of the resulting column stays equal to
    base_score; only the spread across zones changes. Zones missing from
    infra_weights (e.g. zero infrastructure) get a multiplier of 0."""
    n_zones = risk["zone_id"].nunique()
    w = risk[["zone_id"]].merge(infra_weights[["zone_id", "infra_weight"]], on="zone_id", how="left")
    w["infra_weight"] = w["infra_weight"].fillna(0.0)
    multiplier = w["infra_weight"].to_numpy() * n_zones
    return pd.Series(np.clip(base_score * multiplier, 0, 100), index=risk.index)


def build_risk_table(
    grid: pd.DataFrame,
    live_heat: pd.DataFrame,
    vulnerability_joined: pd.DataFrame,
    lines_joined: pd.DataFrame,
    demand_score: float,       # system-wide value, redistributed across zones via infra_weight below
    outage_score: float,       # pre-computed, same value for every zone by design (Texas-specific)
    infra_weights: pd.DataFrame = None,  # from Section 1.3c - enables demand spatial redistribution
) -> pd.DataFrame:
    """Combines 5 components into one grid_heat_risk score per zone."""
    heat = live_heat[["zone_id", "heat_raw_f"]].rename(columns={"heat_raw_f": "heat_raw"})
    infra = lines_joined.groupby("zone_id").size().rename("infra_raw").reset_index()
    vuln = vulnerability_joined[["zone_id", "P_DEMOGIDX_5"]].rename(columns={"P_DEMOGIDX_5": "vuln_raw"})

    all_zones = grid[["zone_id"]].drop_duplicates()
    risk = (
        all_zones.merge(heat, on="zone_id", how="left")
        .merge(infra, on="zone_id", how="left")
        .merge(vuln, on="zone_id", how="left")
    )
    risk["infra_raw"] = risk["infra_raw"].astype(float).fillna(0.0)

    if risk["heat_raw"].isna().any():
        risk["heat_raw"] = risk["heat_raw"].fillna(risk["heat_raw"].mean())

    risk["heat_score"] = normalize_0_100(risk["heat_raw"])

    if infra_weights is not None and not infra_weights.empty:
        risk["demand_score"] = apply_infra_reweighting(risk, demand_score, infra_weights)
    else:
        risk["demand_score"] = demand_score

    risk["infra_score"] = normalize_0_100(risk["infra_raw"])
    risk["outage_score"] = outage_score  # flat broadcast - not reweighted by infra (see module docstring)
    risk["vuln_score"] = normalize_0_100(risk["vuln_raw"])

    risk["grid_heat_risk"] = (
        risk["heat_score"] * RISK_WEIGHTS["heat"]
        + risk["demand_score"] * RISK_WEIGHTS["demand"]
        + risk["infra_score"] * RISK_WEIGHTS["infrastructure"]
        + risk["outage_score"] * RISK_WEIGHTS["outage"]
        + risk["vuln_score"] * RISK_WEIGHTS["vulnerability"]
    )
    return risk.sort_values("grid_heat_risk", ascending=False).reset_index(drop=True)
