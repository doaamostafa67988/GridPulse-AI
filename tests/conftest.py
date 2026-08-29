"""
Shared fixtures for the GridHeat AI (Texas pilot) test suite. Everything
here is synthetic - no real FortyGuard API key, no downloaded data/ files,
no network calls - so `pytest` runs the same way on any machine, including CI.
"""
import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box


@pytest.fixture
def sample_grid() -> gpd.GeoDataFrame:
    """3 adjacent 0.01-degree cells, matching the real grid's cell size and CRS."""
    cells = [box(0.0, 0.0, 0.01, 0.01), box(0.01, 0.0, 0.02, 0.01), box(0.02, 0.0, 0.03, 0.01)]
    return gpd.GeoDataFrame({"zone_id": ["Z00000", "Z00001", "Z00002"], "geometry": cells}, crs="EPSG:4326")


@pytest.fixture
def sample_lines_joined() -> pd.DataFrame:
    """Z00000 has 2 transmission lines, Z00001 has 1, Z00002 has 0."""
    return pd.DataFrame({
        "zone_id": ["Z00000", "Z00000", "Z00001"],
        "OBJECTID": [101, 102, 103],
    })


@pytest.fixture
def sample_vulnerability_joined() -> pd.DataFrame:
    """EJScreen's P_DEMOGIDX_5 (Supplemental Demographic Index percentile),
    used instead of CalEnviroScreen's CIscore - see notebook Section 1.5."""
    return pd.DataFrame({
        "zone_id": ["Z00000", "Z00001", "Z00002"],
        "P_DEMOGIDX_5": [80.0, 40.0, 10.0],
    })


@pytest.fixture
def sample_live_heat() -> pd.DataFrame:
    """Z00000 is hottest, Z00002 is coolest."""
    return pd.DataFrame({
        "zone_id": ["Z00000", "Z00001", "Z00002"],
        "heat_raw_f": [105.0, 95.0, 85.0],
        "as_of_date": ["2026-07-15"] * 3,
    })


@pytest.fixture
def sample_infra_weights() -> pd.DataFrame:
    """Z00000 has the most infrastructure, Z00002 has none - used to spread
    the single system-wide demand_score across zones (Texas-specific, see
    backend/risk_engine.py's apply_infra_reweighting)."""
    return pd.DataFrame({
        "zone_id": ["Z00000", "Z00001", "Z00002"],
        "n_substations": [2, 1, 0],
        "n_transmission_lines": [2, 1, 0],
        "infra_weight": [0.6, 0.4, 0.0],
    })


class MockFortyGuardClient:
    """Stands in for fortyguard.FortyGuardClient - create_heatmap returns a
    canned response covering `sample_grid` exactly, so fetch_live_heat_by_zone
    can run against it with no real API call."""

    def __init__(self, mean_temp_c: float = 38.0):
        self.mean_temp_c = mean_temp_c
        self.calls = []

    def create_heatmap(self, polygon_aoi, start_date, filter_type, granularity):
        self.calls.append({"polygon_aoi": polygon_aoi, "start_date": start_date})
        # One tile per grid cell, covering the whole sample_grid fixture,
        # all at the same fixed temperature for simplicity.
        tiles = []
        for x0 in (0.0, 0.01, 0.02):
            tiles.append({
                "type": "Feature",
                "properties": {"average_temperature": self.mean_temp_c},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[x0, 0.0], [x0 + 0.01, 0.0], [x0 + 0.01, 0.01], [x0, 0.01], [x0, 0.0]]],
                },
            })
        return {
            "activity_id": "test-activity-id",
            "result": {
                "map_data": {"type": "FeatureCollection", "features": tiles},
                "stats_data": {"temperature_stats": {"mean": self.mean_temp_c}},
            },
        }

    def environmental_parameters(self, **kwargs):
        return {"result": {"locations": []}}


@pytest.fixture
def mock_fg_client() -> MockFortyGuardClient:
    return MockFortyGuardClient()


class MockDemandBundle(dict):
    """Stands in for the {"linear", "multivariate", "features"} bundle
    saved by notebook Section 4-FINAL. Both models are fixed linear
    functions of avg_temp_f, so tests get deterministic output; the
    multivariate model is deliberately absent by default so tests exercise
    the "linear (fallback)" path unless a test explicitly adds one."""

    class _LinearModel:
        def predict(self, X):
            return (X["avg_temp_f"] * 50 + 5000).to_numpy()

    def __init__(self):
        super().__init__(linear=self._LinearModel(), multivariate=None, features=[])


@pytest.fixture
def mock_demand_model() -> MockDemandBundle:
    return MockDemandBundle()
