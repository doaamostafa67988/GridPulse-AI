"use client";

import { useEffect, useState } from "react";
import { Sparkles, Thermometer } from "lucide-react";

import { api, MapResponse, MetaResponse, ZoneRisk } from "@/lib/api";
import { splitIntoParagraphs } from "@/lib/format";
import { MapView } from "@/components/MapView";
import { MockDataBanner } from "@/components/MockDataBanner";
import { RiskBadge } from "@/components/RiskBadge";
import { Spinner, ErrorPanel } from "@/components/Feedback";

export default function MapPage() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [mapData, setMapData] = useState<MapResponse | null>(null);
  const [riskByZone, setRiskByZone] = useState<Record<string, ZoneRisk> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);

  useEffect(() => {
    Promise.all([api.getMeta(), api.getMapData(), api.getRiskTable()])
      .then(([m, d, rows]) => {
        setMeta(m);
        setMapData(d);
        setRiskByZone(Object.fromEntries(rows.map((r) => [r.zone_id, r])));
      })
      .catch((e) => setError(e.message ?? "Unknown error"));
  }, []);

  function handleSelectZone(zoneId: string) {
    setSelectedZone(zoneId);
    setExplanation(null);
  }

  async function handleExplain() {
    if (!selectedZone) return;
    setExplainLoading(true);
    setExplanation(null);
    try {
      const res = await api.explainZone(selectedZone);
      setExplanation(res.explanation);
    } catch (e) {
      setExplanation(e instanceof Error ? `Error: ${e.message}` : "Failed to generate explanation.");
    } finally {
      setExplainLoading(false);
    }
  }

  if (error) return <ErrorPanel message={error} />;
  if (!mapData || !meta || !riskByZone) return <Spinner label="Loading map data..." />;

  const selected = selectedZone ? riskByZone[selectedZone] : null;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <div className="mb-6 shrink-0">
        <h1 className="text-2xl font-semibold text-foreground">Map View</h1>
        <p className="mt-1 text-sm text-muted">
          Grid heat risk by zone, with nearby transmission infrastructure. Click a zone for details.
        </p>
      </div>

      {meta.using_mock_data && (
        <div className="shrink-0">
          <MockDataBanner />
        </div>
      )}

      <div className="flex min-h-0 flex-1 gap-4">
        <div className="panel flex min-h-0 flex-[2] flex-col p-3">
          <MapView data={mapData} onSelectZone={handleSelectZone} />
        </div>

        <div className="panel flex w-80 shrink-0 flex-col overflow-y-auto p-4">
          {!selected && (
            <p className="text-sm text-muted">Click a zone on the map to see its risk breakdown here.</p>
          )}

          {selected && (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground">{selected.zone_id}</h2>
                <RiskBadge score={selected.grid_heat_risk} />
              </div>

              {selected.heat_raw_f != null && (
                <div className="mt-3 flex items-center gap-1.5 rounded-lg bg-orange-50 px-3 py-2 text-orange-700">
                  <Thermometer size={16} />
                  <span className="text-lg font-semibold">{selected.heat_raw_f.toFixed(1)}°F</span>
                  <span className="text-xs text-orange-700/70">current zone temperature</span>
                </div>
              )}

              <div className="mt-4 space-y-2.5 text-sm">
                <ScoreRow label="Heat (0–100)" value={selected.heat_score} />
                <ScoreRow label="Demand" value={selected.demand_score} />
                <ScoreRow label="Infrastructure" value={selected.infra_score} />
                <ScoreRow label="Outage history" value={selected.outage_score} />
                <ScoreRow label="Vulnerability" value={selected.vuln_score} />
              </div>

              <div className="mt-5 border-t border-panel-border pt-4">
                <button
                  onClick={handleExplain}
                  disabled={explainLoading}
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  <Sparkles size={15} />
                  Why was this zone flagged?
                </button>
                {explainLoading && <Spinner label="Generating explanation..." />}
                {explanation && (
                  <div className="mt-3 max-w-full space-y-2 break-words rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm leading-relaxed text-blue-900">
                    {splitIntoParagraphs(explanation).map((para, i) => (
                      <p key={i}>{para}</p>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <div className="mt-4 flex shrink-0 flex-wrap items-center gap-6 text-xs text-muted">
        <LegendSwatch color="#16a34a" label="Low risk (< 40)" />
        <LegendSwatch color="#f59e0b" label="Moderate risk (40–60)" />
        <LegendSwatch color="#dc2626" label="High risk (≥ 60)" />
        <LegendSwatch color="#d1d5db" label="No data" />
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 bg-foreground" />
          Transmission line
        </span>
      </div>
    </div>
  );
}

function ScoreRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted">{label}</span>
      <span className="font-medium text-foreground">{value.toFixed(1)}</span>
    </div>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
