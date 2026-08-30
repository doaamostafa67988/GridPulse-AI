# Data Sources & Licenses — GridHeat AI (Texas Pilot)

**Notebook:** `GridHeat_AI_Pipeline_Texas_v7.ipynb`
**Last verified:** August 29, 2026 — every URL below was tested live on this date.

> This project combines six external data sources: five public U.S. government datasets and one commercial API. The license terms differ significantly between the two groups — see the note at the end.

---

## 1. HIFLD — Electric Substations (point layer)

| Field | Value |
|---|---|
| **Used in notebook** | Section 1.1 (Cell 6) |
| **Data URL** | `https://services5.arcgis.com/HDRa0B57OVrv2E1q/arcgis/rest/services/Electric_Substations/FeatureServer/0` |
| **License** | U.S. federal geospatial data — public domain in principle, but HIFLD states some layers carry their own terms; check item-level details |
| **Terms of use** | ⚠️ The original page (`https://hifld-geoplatform.hub.arcgis.com/pages/hifld-terms-of-use`) is **dead** — it returns an "Invalid client_id" login error, confirmed by direct testing on 8/29/2026. The quote I previously put here ("Some HIFLD data may be subject to copyright restrictions...") came from an old cached search-engine snippet of that page, **not** from a page I could actually open — I should not have presented it as a working link. I cannot currently verify that exact text against a live source. |
| **What's actually verifiable now** | The HIFLD Open portal was decommissioned by DHS on 8/26/2025. The datasets carried no proprietary claim — they originated as U.S. federal public-domain data. One archived copy (SeerAI) explicitly states its re-packaged version is released under **CC BY 4.0**: https://source.coop/seerai/hifld. Another archival effort (ICPSR/DataLumos) also confirms the 8/26/2025 deactivation date: https://www.datalumos.org/datalumos/project/241367/version/V1/view |
| **Fallback source if this endpoint goes down** | HIFLD Next (community-preserved archive): https://hifld.publicenvirodata.org/ |

## 2. HIFLD — US Electric Power Transmission Lines (line layer)

| Field | Value |
|---|---|
| **Used in notebook** | Section 1.1 (Cell 6) |
| **Data URL** | `https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/US_Electric_Power_Transmission_Lines/FeatureServer/0` |
| **License** | Same as above — U.S. federal geospatial data |
| **Terms of use** | ⚠️ Same dead link as the substations entry above (`hifld-geoplatform.hub.arcgis.com/pages/hifld-terms-of-use`) — see the correction there. Use the SeerAI (CC BY 4.0) and DataLumos/ICPSR archives instead for verifiable licensing info. |
| **Fallback source** | HIFLD Next: https://hifld.publicenvirodata.org/ |

> ⚠️ **Important — HIFLD Open portal status:** DHS discontinued the public **HIFLD Open** catalog/portal on **August 26, 2025**. The two REST endpoints above still work because they are hosted on independent ArcGIS Online organizations, not on the portal that was shut down. There is no guarantee they will stay online indefinitely. If either breaks, re-source the same layers from **HIFLD Next** (https://hifld.publicenvirodata.org/), a community-maintained archive built from a full pre-shutdown snapshot.

## 3. DOE / ORNL EAGLE-I — County-Level Power Outages

| Field | Value |
|---|---|
| **Used in notebook** | Section 1.2 (Cell 9) — loaded from a Google Drive-hosted `eaglei_outages_2024.zip` |
| **License** | U.S. federal government work — public domain; citation requested. Legal basis: 17 U.S.C. §105 (https://www.govinfo.gov/content/pkg/USCODE-2020-title17/html/USCODE-2020-title17-chap1-sec105.htm). DOE/OSTI's own explanation of how this applies to their published datasets: https://www.osti.gov/stip/submit/submission-basics/sti-copyright |
| **Actual source used** | https://figshare.com/articles/dataset/The_Environment_for_Analysis_of_Geo-Located_Energy_Information_s_Recorded_Electricity_Outages_2014-2022/24237376 |
| **Official DOE/OSTI source / DOI (not what was used here, listed for reference)** | https://doi.org/10.13139/ORNLNCCS/3012826 (2025 release; 2024 release: https://doi.org/10.13139/OLCF/2500278 — note the different prefix, **OLCF** not ORNLNCCS, confirmed against the OSTI.GOV record for OSTI ID 2500278) |
| **Recommended citation** | Tansakul, V., Myers, A., Tennille, S., et al. *EAGLE-I Power Outage Data.* Oak Ridge National Laboratory. DOE/ORNL. |

## 4. EIA-930 — ERCOT Hourly Electricity Demand (via EIA Open Data API)

| Field | Value |
|---|---|
| **Used in notebook** | Section 1.3 (Cell 13) |
| **API endpoint used by the code** | `https://api.eia.gov/v2/electricity/rto/region-data/data/` (route confirmed correct for balancing-authority-level demand — `facets[respondent][]=ERCO`) |
| **Registration (required, free)** | https://www.eia.gov/opendata/register.php |
| **License** | Free to use; governed by the EIA API Terms of Service — attribution to "U.S. Energy Information Administration (EIA)" requested |
| **Terms of Service** | https://www.eia.gov/opendata/terms-of-service.php |

## 5. EIA-860 — Battery Storage (BESS), Texas

| Field | Value |
|---|---|
| **Used in notebook** | Section 1.4 (Cell 15) — manual upload of the EIA-860 annual release zip, filtered to `State == "TX"` |
| **License** | Same EIA license/ToS as above (public data, free to use, attribution requested) |
| **Official source** | https://www.eia.gov/electricity/data/eia860/ |

## 6. EPA EJScreen — Environmental & Social Vulnerability, Texas (tract level)

| Field | Value |
|---|---|
| **Used in notebook** | Section 1.5 (Cells 17–18) — manual upload of `EJScreen_2024_Tract_with_AS_CNMI_GU_VI.csv.zip`, joined to geometry via Census TIGER boundaries |
| **License** | U.S. federal government work — public domain |
| **Status** | ⚠️ EPA discontinued the live EJScreen tool and its ArcGIS FeatureServer on **February 5, 2025**. The only path to this data now is an archived copy. |
| **Actual source used** | University of Chicago's Federal Data Rescue Project (Box-hosted mirror), not fetched directly from EPA: https://uchicago.app.box.com/s/tkfpbv1xd2lbh7deykpjtscha4739k00 |
| **Source record / license page** | https://knowledge.uchicago.edu/records/z7nbk-5bk41 — states: *"Copyrights: This dataset was downloaded from a federal government website and remains in the public domain."* The "Distribution License" listed there (https://knowledge.uchicago.edu/distribution-license) governs UChicago's right to host/redistribute the archived copy — it is not a new license on the underlying EPA data, which stays public domain. |
| **Other archived copies (not what was used here, listed for reference)** | Official EPA archive: https://gaftp.epa.gov/EJScreen/ · Zenodo mirror: https://zenodo.org/records/14767363 |
| **Companion boundary file used by the code** | `https://www2.census.gov/geo/tiger/GENZ{year}/shp/cb_{year}_48_tract_500k.zip` (Census TIGER cartographic boundary, Texas tracts; `48` = Texas FIPS code) |

## 7. FortyGuard — Temperature API (commercial, not public data)

| Field | Value |
|---|---|
| **Used in notebook** | Section 0 (setup), Section 5 (live heat), Section 4 (historical temperature for demand model) |
| **Nature of source** | ⚠️ **Commercial paid API** — not a public/open dataset like the six sources above |
| **License** | Governed by FortyGuard's own commercial API agreement / Terms of Service, not an open license. No public ToS page was found on their site as of this check. |
| **Where to check terms** | https://www.fortyguard.com/api-pricing, or the agreement presented when the API key was generated |
| **Action needed** | Before publishing or redistributing any notebook output that includes FortyGuard temperature values (maps, dashboards, csvs), confirm redistribution rights directly with FortyGuard — public-domain assumptions do **not** apply here. |

