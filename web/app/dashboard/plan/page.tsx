"use client";

import { useEffect, useState } from "react";
import { Sparkles, AlertCircle } from "lucide-react";

import { api, MetaResponse, PlanResponse, ZoneRisk } from "@/lib/api";
import { formatCurrency, actionLabel, splitIntoParagraphs } from "@/lib/format";
import { RiskBadge } from "@/components/RiskBadge";
import { MockDataBanner } from "@/components/MockDataBanner";
import { Spinner, ErrorPanel } from "@/components/Feedback";

const DISCLAIMER =
  "Modeling assumption, not operational fact. Action costs and risk-reduction percentages are scenario " +
  "assumptions used to demonstrate constrained optimization — not utility-specific cost estimates or " +
  "empirically calibrated intervention effects. Heat, demand, transmission lines, and vulnerability scores " +
  "are computed from the underlying data; the dollar figures and % reductions for each action are " +
  "illustrative placeholders.";

export default function PlanPage() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [criticalZones, setCriticalZones] = useState<ZoneRisk[] | null>(null);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [budget, setBudget] = useState(50_000);
  const [resolvedBudget, setResolvedBudget] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const planLoading = resolvedBudget !== budget;

  const [selectedZone, setSelectedZone] = useState<string>("");
  const [zoneExplanation, setZoneExplanation] = useState<string | null>(null);
  const [zoneExplainLoading, setZoneExplainLoading] = useState(false);

  const [planExplanation, setPlanExplanation] = useState<string | null>(null);
  const [planExplainLoading, setPlanExplainLoading] = useState(false);

  useEffect(() => {
    Promise.all([api.getMeta(), api.getCriticalZones()])
      .then(([m, zones]) => {
        setMeta(m);
        setCriticalZones(zones);
        if (zones.length) setSelectedZone(zones[0].zone_id);
      })
      .catch((e) => setError(e.message ?? "Unknown error"));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .getPlan(budget)
      .then((res) => {
        if (!cancelled) {
          setPlan(res);
          setPlanExplanation(null);
          setResolvedBudget(budget);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e.message ?? "Unknown error");
          setResolvedBudget(budget);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [budget]);

  async function handleExplainZone() {
    if (!selectedZone) return;
    setZoneExplainLoading(true);
    setZoneExplanation(null);
    try {
      const res = await api.explainZone(selectedZone);
      setZoneExplanation(res.explanation);
    } catch (e) {
      setZoneExplanation(e instanceof Error ? `Error: ${e.message}` : "Failed to generate explanation.");
    } finally {
      setZoneExplainLoading(false);
    }
  }

  async function handleExplainPlan() {
    setPlanExplainLoading(true);
    setPlanExplanation(null);
    try {
      const res = await api.explainPlan(budget);
      setPlanExplanation(res.explanation);
    } catch (e) {
      setPlanExplanation(e instanceof Error ? `Error: ${e.message}` : "Failed to generate explanation.");
    } finally {
      setPlanExplainLoading(false);
    }
  }

  if (error) return <ErrorPanel message={error} />;
  if (!meta || !criticalZones) return <Spinner label="Loading critical zones..." />;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-foreground">Critical Zones & Recommended Plan</h1>
        <p className="mt-1 text-sm text-muted">
          Budget-constrained resilience actions selected by exact 0/1 knapsack optimization.
        </p>
      </div>

      {meta.using_mock_data && <MockDataBanner />}

      {!meta.llm_configured && (
        <div className="mb-6 flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <p>
            GROQ_API_KEY isn&apos;t configured on the backend — &ldquo;Why?&rdquo; explanations below will show a
            plain evidence summary instead of an LLM-generated one.
          </p>
        </div>
      )}

      <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
        ⚠️ {DISCLAIMER}
      </div>

      <div className="mb-6 panel p-5">
        <div className="flex items-center justify-between">
          <label htmlFor="budget" className="text-sm font-semibold text-foreground">
            Budget: {formatCurrency(budget)}
          </label>
          <span className="text-xs text-muted">$10,000 – $100,000</span>
        </div>
        <input
          id="budget"
          type="range"
          min={10_000}
          max={100_000}
          step={5_000}
          value={budget}
          onChange={(e) => setBudget(Number(e.target.value))}
          className="mt-3 w-full accent-brand"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:[&>*]:min-w-0">
        {/* Critical zones */}
        <div className="panel p-5">
          <h2 className="mb-4 text-sm font-semibold text-foreground">
            Critical zones <span className="text-muted">({criticalZones.length})</span>
          </h2>

          {criticalZones.length === 0 ? (
            <p className="text-sm text-muted">No critical zones at the current threshold.</p>
          ) : (
            <div className="max-h-80 overflow-y-auto rounded-lg border border-panel-border">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 border-b border-panel-border bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 font-semibold text-muted">Zone</th>
                    <th className="px-3 py-2 font-semibold text-muted">Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {criticalZones.map((z) => (
                    <tr key={z.zone_id} className="border-b border-panel-border last:border-0">
                      <td className="px-3 py-2">{z.zone_id}</td>
                      <td className="px-3 py-2">
                        <RiskBadge score={z.grid_heat_risk} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="mt-5 border-t border-panel-border pt-5">
            <p className="mb-2 text-sm font-semibold text-foreground">Why was a zone flagged?</p>
            <div className="flex gap-2">
              <select
                value={selectedZone}
                onChange={(e) => setSelectedZone(e.target.value)}
                className="flex-1 rounded-lg border border-panel-border bg-white px-3 py-2 text-sm"
              >
                {criticalZones.map((z) => (
                  <option key={z.zone_id} value={z.zone_id}>
                    {z.zone_id}
                  </option>
                ))}
              </select>
              <button
                onClick={handleExplainZone}
                disabled={zoneExplainLoading || !selectedZone}
                className="flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                <Sparkles size={15} />
                Why?
              </button>
            </div>
            {zoneExplainLoading && <Spinner label="Generating explanation..." />}
            {zoneExplanation && (
              <div className="mt-3 max-w-full space-y-2 break-words rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm leading-relaxed text-blue-900">
                {splitIntoParagraphs(zoneExplanation).map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Recommended plan */}
        <div className="panel p-5">
          <h2 className="mb-4 text-sm font-semibold text-foreground">Recommended plan</h2>

          {planLoading || !plan ? (
            <Spinner label="Optimizing plan..." />
          ) : plan.actions.length === 0 ? (
            <p className="text-sm text-muted">No actions selected within this budget.</p>
          ) : (
            <div className="max-h-80 overflow-y-auto rounded-lg border border-panel-border">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 border-b border-panel-border bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 font-semibold text-muted">Zone</th>
                    <th className="px-3 py-2 font-semibold text-muted">Action</th>
                    <th className="px-3 py-2 font-semibold text-muted">Cost</th>
                    <th className="px-3 py-2 font-semibold text-muted">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.actions.map((a, i) => (
                    <tr key={i} className="border-b border-panel-border last:border-0">
                      <td className="px-3 py-2">{a.zone_id}</td>
                      <td className="px-3 py-2">{actionLabel(a.action)}</td>
                      <td className="px-3 py-2">{formatCurrency(a.cost)}</td>
                      <td className="px-3 py-2">{a.value.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {plan && (
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-lg bg-gray-50 p-3">
                <p className="text-xs text-muted">Total cost</p>
                <p className="text-lg font-semibold text-foreground">
                  {formatCurrency(plan.total_cost)}{" "}
                  <span className="text-sm font-normal text-muted">/ {formatCurrency(budget)}</span>
                </p>
              </div>
              <div className="rounded-lg bg-gray-50 p-3">
                <p className="text-xs text-muted">Risk-reduction value</p>
                <p className="text-lg font-semibold text-foreground">{plan.total_value.toFixed(2)}</p>
              </div>
            </div>
          )}

          <div className="mt-5 border-t border-panel-border pt-5">
            <p className="mb-2 text-sm font-semibold text-foreground">Why this plan?</p>
            <button
              onClick={handleExplainPlan}
              disabled={planExplainLoading || !plan || plan.actions.length === 0}
              className="flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              <Sparkles size={15} />
              Why this plan?
            </button>
            {planExplainLoading && <Spinner label="Generating explanation..." />}
            {planExplanation && (
              <div className="mt-3 max-w-full space-y-2 break-words rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm leading-relaxed text-blue-900">
                {splitIntoParagraphs(planExplanation).map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
