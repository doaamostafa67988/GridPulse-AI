/**
 * Typed client for the GridHeat AI FastAPI backend (backend/api.py).
 * Base URL comes from NEXT_PUBLIC_API_URL (see .env.local.example) - falls
 * back to localhost:8000 for local dev with `uvicorn backend.api:app`.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ZoneRisk {
  zone_id: string;
  grid_heat_risk: number;
  heat_score: number;
  demand_score: number;
  infra_score: number;
  outage_score: number;
  vuln_score: number;
  /** Actual temperature in °F, when the backend has it (see backend/api.py). */
  heat_raw_f: number | null;
}

export interface MetaResponse {
  using_mock_data: boolean;
  n_zones: number;
  n_critical_zones: number;
  risk_threshold: number;
  llm_configured: boolean;
}

export interface PlanAction {
  zone_id: string;
  action: string;
  cost: number;
  value: number;
}

export interface ActionSpec {
  cost: number;
  risk_reduction_pct: number;
  requires_battery: boolean;
}

export interface PlanResponse {
  budget: number;
  total_cost: number;
  total_value: number;
  actions: PlanAction[];
  action_catalog: Record<string, ActionSpec>;
}

export interface MapResponse {
  grid: GeoJSON.FeatureCollection;
  lines: GeoJSON.FeatureCollection;
}

export interface ExplainZoneResponse {
  zone_id: string;
  explanation: string;
}

export interface ExplainPlanResponse {
  explanation: string;
  total_cost: number;
  total_value: number;
  budget: number;
}

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore - use statusText
    }
    throw new ApiError(detail, res.status);
  }
  return res.json();
}

export const api = {
  getMeta: () => apiFetch<MetaResponse>("/api/meta"),
  getRiskTable: () => apiFetch<ZoneRisk[]>("/api/risk-table"),
  getCriticalZones: (threshold?: number) =>
    apiFetch<ZoneRisk[]>(`/api/critical-zones${threshold != null ? `?threshold=${threshold}` : ""}`),
  getMapData: () => apiFetch<MapResponse>("/api/map"),
  getPlan: (budget: number) => apiFetch<PlanResponse>(`/api/plan?budget=${budget}`),
  explainZone: (zoneId: string) =>
    apiFetch<ExplainZoneResponse>(`/api/explain/zone/${encodeURIComponent(zoneId)}`),
  explainPlan: (budget: number) =>
    apiFetch<ExplainPlanResponse>("/api/explain/plan", {
      method: "POST",
      body: JSON.stringify({ budget }),
    }),
};

export { ApiError };
