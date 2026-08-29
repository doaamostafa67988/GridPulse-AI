"""
GridHeat AI - Streamlit frontend, Texas (Harris County / Houston) pilot.

Imports backend functions directly (same process, no HTTP API) - see the
architecture note in README.md for why. Run from the repo root:

    streamlit run frontend/app.py

Requires the data/ folder to contain the artifact files listed in
backend/config.py (copy them from the Colab notebook's outputs), plus
FORTYGUARD_API_KEY and (optionally) GROQ_API_KEY in Streamlit secrets
(.streamlit/secrets.toml locally, or the Streamlit Cloud secrets UI when
deployed) for the live-refresh and "Why?" buttons to work.
"""
import sys
from pathlib import Path

# Allow `from backend import ...` when run as `streamlit run frontend/app.py`
# from the repo root, without needing to install the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import folium
import branca.colormap as cm
import geopandas as gpd
import pandas as pd
import streamlit as st

from backend import data_access
from backend.config import ACTIONS, DEFAULT_RISK_THRESHOLD, PILOT_CRS
from backend.llm_explain import build_zone_evidence, explain_plan, explain_zone, get_groq_client
from backend.optimization import build_candidate_options, optimize_plan, summarize_plan

st.set_page_config(page_title="GridHeat AI - Harris County (Houston) Pilot", layout="wide")

DISCLAIMER_MD = (
    "> ⚠️ **Modeling assumption, not operational fact.** Action costs and "
    "risk-reduction percentages below are scenario assumptions used to "
    "demonstrate constrained optimization - not utility-specific cost "
    "estimates or empirically calibrated intervention effects. Heat, "
    "ERCOT demand, transmission lines, EAGLE-I outage history, EPA "
    "EJScreen vulnerability, and battery storage locations are real "
    "public Texas data; the dollar figures and % reductions for each "
    "action are illustrative placeholders."
)


@st.cache_data
def load_risk_table() -> pd.DataFrame:
    return data_access.load_risk_table()


@st.cache_data
def load_grid_and_lines():
    grid = data_access.load_grid()
    lines = data_access.load_transmission_lines()
    return grid, lines


@st.cache_data
def load_battery() -> pd.DataFrame:
    return data_access.load_battery_joined()


@st.cache_data
def load_lines_joined() -> pd.DataFrame:
    return data_access.load_lines_joined()


@st.cache_resource
def load_groq_client():
    """Cached separately from st.cache_data since a client is a resource,
    not serializable data. Returns None if GROQ_API_KEY isn't configured -
    callers (explain_zone/explain_plan) already degrade gracefully to a
    template explanation in that case."""
    return get_groq_client()


def build_map_html(risk_table: pd.DataFrame, grid: gpd.GeoDataFrame, lines: gpd.GeoDataFrame) -> str:
    grid_wgs = grid.to_crs("EPSG:4326").merge(risk_table[["zone_id", "grid_heat_risk"]], on="zone_id", how="left")
    lines_wgs = lines.to_crs("EPSG:4326")

    center_point = grid_wgs.to_crs(PILOT_CRS).geometry.union_all().centroid
    center_wgs = gpd.GeoSeries([center_point], crs=PILOT_CRS).to_crs("EPSG:4326").iloc[0]

    m = folium.Map(location=[center_wgs.y, center_wgs.x], zoom_start=12, tiles="CartoDB positron")

    colormap = cm.LinearColormap(
        colors=["#fee8c8", "#fdbb84", "#e34a33"],
        vmin=risk_table["grid_heat_risk"].min(), vmax=risk_table["grid_heat_risk"].max(),
        caption="Grid Heat Risk",
    )
    colormap.add_to(m)

    folium.GeoJson(
        grid_wgs,
        style_function=lambda feature: {
            "fillColor": colormap(feature["properties"]["grid_heat_risk"]),
            "color": "gray", "weight": 0.5, "fillOpacity": 0.7,
        },
        tooltip=folium.GeoJsonTooltip(fields=["zone_id", "grid_heat_risk"], aliases=["Zone", "Risk"]),
    ).add_to(m)

    folium.GeoJson(lines_wgs, style_function=lambda f: {"color": "black", "weight": 2}).add_to(m)
    return m._repr_html_()


def main():
    st.title("GridHeat AI — Harris County (Houston) Pilot")

    try:
        risk_table = load_risk_table()
    except FileNotFoundError as e:
        st.error(str(e))
        st.info("Run `python -m backend.graph` (or the notebook's LangGraph section) at least once to generate tx_risk_table.csv.")
        return

    critical_zones = risk_table[risk_table["grid_heat_risk"] >= DEFAULT_RISK_THRESHOLD].copy()
    st.caption(f"{len(risk_table)} zones · {len(critical_zones)} above risk threshold {DEFAULT_RISK_THRESHOLD}")

    tab1, tab2, tab3 = st.tabs(["Risk Overview", "Map View", "Critical Zones + Recommended Plan"])

    with tab1:
        display_cols = ["zone_id", "grid_heat_risk", "heat_score", "demand_score",
                         "infra_score", "outage_score", "vuln_score"]
        st.dataframe(risk_table[display_cols].round(2), width="stretch")

    with tab2:
        grid, lines = load_grid_and_lines()
        st.components.v1.html(build_map_html(risk_table, grid, lines), height=600)

    with tab3:
        st.markdown(DISCLAIMER_MD)
        battery_joined = load_battery()
        lines_joined = load_lines_joined()
        groq_client = load_groq_client()
        if groq_client is None:
            st.caption("ℹ️ GROQ_API_KEY not set - \"Why?\" explanations will show a plain evidence summary instead of an LLM explanation. See .env.example.")

        budget = st.slider("Budget ($)", min_value=10_000, max_value=100_000, value=50_000, step=5_000)

        options = build_candidate_options(critical_zones, battery_joined)
        result = optimize_plan(options, budget)
        plan_df = summarize_plan(result)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Critical zones")
            st.dataframe(critical_zones[["zone_id", "grid_heat_risk"]].round(2), width="stretch")

            st.markdown("**Why was a zone flagged?**")
            zone_choices = critical_zones["zone_id"].tolist()
            if zone_choices:
                selected_zone = st.selectbox("Zone", zone_choices, key="zone_explain_select")
                if st.button("Why?", key="why_zone_btn"):
                    evidence = build_zone_evidence(selected_zone, risk_table, lines_joined, battery_joined)
                    with st.spinner("Generating explanation..."):
                        st.info(explain_zone(groq_client, evidence))
            else:
                st.caption("No critical zones to explain at the current threshold.")

        with col2:
            st.subheader("Recommended plan")
            st.dataframe(plan_df, width="stretch")

            st.markdown("**Why this plan?**")
            if st.button("Why this plan?", key="why_plan_btn"):
                if plan_df.empty:
                    st.info("No actions were selected within this budget, so there's no plan to explain.")
                else:
                    with st.spinner("Generating explanation..."):
                        st.info(explain_plan(groq_client, plan_df, result["total_cost"], result["total_value"], budget))

        st.metric("Total cost", f"${result['total_cost']:,} / ${budget:,}")
        st.metric("Risk-reduction value", f"{result['total_value']:.2f}")


if __name__ == "__main__":
    main()
