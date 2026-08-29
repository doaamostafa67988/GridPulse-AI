"""
Deterministic mock data generator, used by backend/api.py when the real
artifact files (backend/config.py's DATA_DIR paths, produced by
notebooks/GridHeat_AI_Pipeline_Texas.ipynb) aren't present in data/. This
lets the FastAPI layer - and the Next.js frontend behind it - run and be
demoed with zero setup: no data pipeline run, no
FORTYGUARD_API_KEY/GROQ_API_KEY needed.

Every zone/grid cell here is a synthetic placeholder over a small area near
Harris County (Houston), TX (not real geometry) - clearly fake, but shaped
exactly like the real artifacts so backend/risk_engine.py,
backend/optimization.py, and backend/llm_explain.py all run against it
unmodified. Swap in real data by populating data/ per config.py; backend/api.py
then uses that automatically and this module is never called.

random.seed / np.random.seed are fixed so the same mock risk table is
returned across requests without needing to cache/persist it.
"""
import random

import numpy as np
import pandas as pd

N_ZONES = 24
HARRIS_COUNTY_CENTER = (-95.3698, 29.7604)  # (lon, lat) - downtown Houston
CELL_SIZE_DEG = 0.02


def _zone_id(i: int) -> str:
    return f"Z{i:05d}"


def _grid_cell_polygon(cx: float, cy: float, size: float) -> dict:
    half = size / 2
    coords = [
        [cx - half, cy - half], [cx + half, cy - half],
        [cx + half, cy + half], [cx - half, cy + half],
        [cx - half, cy - half],
    ]
    return {"type": "Polygon", "coordinates": [coords]}


def mock_risk_table() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    for i in range(N_ZONES):
        heat = float(rng.uniform(20, 95))
        demand = float(rng.uniform(15, 90))
        infra = float(rng.uniform(10, 80))
        outage = float(rng.uniform(5, 85))
        vuln = float(rng.uniform(10, 90))
        risk = heat * 0.30 + demand * 0.25 + infra * 0.20 + outage * 0.15 + vuln * 0.10
        # Synthetic actual temperature in °F, scaled off the same heat draw
        # so a zone with a high heat_score also shows a plausible high
        # reading here (roughly a Houston-summer 90-120°F range) rather
        # than an unrelated random number.
        heat_raw_f = 90.0 + (heat / 100.0) * 30.0
        rows.append({
            "zone_id": _zone_id(i), "grid_heat_risk": round(risk, 2),
            "heat_score": round(heat, 1), "demand_score": round(demand, 1),
            "infra_score": round(infra, 1), "outage_score": round(outage, 1),
            "vuln_score": round(vuln, 1), "heat_raw_f": round(heat_raw_f, 1),
        })
    return pd.DataFrame(rows)


def mock_grid_geojson() -> dict:
    """A small grid of square cells near Harris County (Houston), one per
    zone - fake geometry, real-shaped GeoJSON FeatureCollection (EPSG:4326)."""
    cols = 6
    features = []
    for i in range(N_ZONES):
        row, col = divmod(i, cols)
        cx = HARRIS_COUNTY_CENTER[0] + (col - cols / 2) * CELL_SIZE_DEG
        cy = HARRIS_COUNTY_CENTER[1] + (row - N_ZONES / cols / 2) * CELL_SIZE_DEG
        features.append({
            "type": "Feature",
            "geometry": _grid_cell_polygon(cx, cy, CELL_SIZE_DEG * 0.9),
            "properties": {"zone_id": _zone_id(i)},
        })
    return {"type": "FeatureCollection", "features": features}


def mock_transmission_lines_geojson() -> dict:
    rng = random.Random(3)
    features = []
    for i in range(5):
        y = HARRIS_COUNTY_CENTER[1] + rng.uniform(-0.06, 0.06)
        x0 = HARRIS_COUNTY_CENTER[0] - 0.09
        x1 = HARRIS_COUNTY_CENTER[0] + 0.09
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[x0, y], [x1, y + rng.uniform(-0.02, 0.02)]]},
            "properties": {"OBJECTID": i + 1},
        })
    return {"type": "FeatureCollection", "features": features}


def mock_battery_joined() -> pd.DataFrame:
    rng = random.Random(11)
    zone_ids = [_zone_id(i) for i in range(N_ZONES)]
    battery_zones = rng.sample(zone_ids, k=6)
    return pd.DataFrame({
        "zone_id": battery_zones,
        "n_battery_sites": [rng.randint(1, 3) for _ in battery_zones],
    })


def mock_lines_joined() -> pd.DataFrame:
    rng = random.Random(13)
    zone_ids = [_zone_id(i) for i in range(N_ZONES)]
    rows = []
    for zone_id in zone_ids:
        for _ in range(rng.randint(0, 3)):
            rows.append({"zone_id": zone_id, "OBJECTID": rng.randint(1, 5)})
    return pd.DataFrame(rows, columns=["zone_id", "OBJECTID"])
