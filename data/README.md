# data/

Empty on purpose (gitignored except this file). If empty, `backend/api.py`
serves synthetic mock data automatically (see `backend/mock_data.py`) so the
app runs with zero setup.

To run against real data, copy these files here from a run of
`notebooks/GridHeat_AI_Pipeline_Texas.ipynb`:

- `harris_aoi_precise.geojson`
- `heat_zone_grid_tx.geojson`
- `tx_substations_clean.geojson`
- `tx_transmission_lines_clean.geojson`
- `ejscreen_tx_clean.geojson`
- `battery_storage_tx_clean.geojson`
- `lines_joined_tx.csv`, `vulnerability_joined_tx.csv`, `battery_joined_tx.csv`
- `infra_weights_tx.csv` (optional - enables spatial redistribution of the
  system-wide demand score; without it, demand_score is broadcast flat)
- `eagle_i_tx_clean.csv`
- `tx_county_scoreboard.csv` (optional - candidate-county outage reference
  range from Section 2's Stage B; without it, the outage reference range
  falls back to `(0, pilot_total)`)
- `ercot_demand_clean.csv`
- `tx_temp_demand_merged.csv`
- `tx_demand_model.joblib` (bundle: `{"linear", "multivariate", "features"}`)
