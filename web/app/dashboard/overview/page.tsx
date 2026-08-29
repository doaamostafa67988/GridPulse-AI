"use client";

import { useEffect, useMemo, useState } from "react";
import { BarChart3, Flame, Grid3x3, ShieldAlert } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";

import { api, MetaResponse, ZoneRisk } from "@/lib/api";
import { riskColor } from "@/lib/format";
import { StatCard } from "@/components/StatCard";
import { RiskBadge } from "@/components/RiskBadge";
import { MockDataBanner } from "@/components/MockDataBanner";
import { Spinner, ErrorPanel } from "@/components/Feedback";

type SortKey = keyof ZoneRisk;

export default function OverviewPage() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [rows, setRows] = useState<ZoneRisk[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("grid_heat_risk");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    Promise.all([api.getMeta(), api.getRiskTable()])
      .then(([m, r]) => {
        setMeta(m);
        setRows(r);
      })
      .catch((e) => setError(e.message ?? "Unknown error"));
  }, []);

  const sortedRows = useMemo(() => {
    if (!rows) return [];
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "string" || typeof bv === "string") {
        return sortDir === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      }
      return sortDir === "asc" ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  const chartData = useMemo(() => {
    if (!rows) return [];
    return [...rows]
      .sort((a, b) => b.grid_heat_risk - a.grid_heat_risk)
      .slice(0, 12)
      .map((r) => ({ zone: r.zone_id.replace("Z", ""), risk: r.grid_heat_risk }));
  }, [rows]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  if (error) return <ErrorPanel message={error} />;
  if (!rows || !meta) return <Spinner label="Loading risk table..." />;

  const columns: { key: SortKey; label: string }[] = [
    { key: "zone_id", label: "Zone" },
    { key: "grid_heat_risk", label: "Risk Score" },
    { key: "heat_score", label: "Heat" },
    { key: "demand_score", label: "Demand" },
    { key: "infra_score", label: "Infra" },
    { key: "outage_score", label: "Outage" },
    { key: "vuln_score", label: "Vulnerability" },
  ];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-foreground">Risk Overview</h1>
        <p className="mt-1 text-sm text-muted">
          Deterministic grid-heat risk scores across all monitored zones.
        </p>
      </div>

      {meta.using_mock_data && <MockDataBanner />}

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total zones" value={String(meta.n_zones)} icon={<Grid3x3 size={18} />} />
        <StatCard
          label="Critical zones"
          value={String(meta.n_critical_zones)}
          hint={`≥ ${meta.risk_threshold} risk threshold`}
          icon={<ShieldAlert size={18} />}
        />
        <StatCard
          label="Avg. risk score"
          value={(rows.reduce((s, r) => s + r.grid_heat_risk, 0) / rows.length).toFixed(1)}
          icon={<Flame size={18} />}
        />
        <StatCard
          label="Highest risk zone"
          value={sortedRows.length ? [...rows].sort((a, b) => b.grid_heat_risk - a.grid_heat_risk)[0].zone_id : "—"}
          icon={<BarChart3 size={18} />}
        />
      </div>

      <div className="panel mb-6 p-5">
        <h2 className="mb-4 text-sm font-semibold text-foreground">Top 12 zones by risk score</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e6e8ec" />
            <XAxis dataKey="zone" tick={{ fontSize: 12 }} stroke="#6b7280" />
            <YAxis tick={{ fontSize: 12 }} stroke="#6b7280" />
            <Tooltip
              contentStyle={{ borderRadius: 8, border: "1px solid #e6e8ec", fontSize: 12 }}
              formatter={(value) => [Number(value ?? 0).toFixed(1), "Risk score"]}
              labelFormatter={(label) => `Zone Z${String(label).padStart(5, "0")}`}
            />
            <Bar dataKey="risk" radius={[4, 4, 0, 0]}>
              {chartData.map((d, i) => (
                <Cell key={i} fill={riskColor(d.risk)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-panel-border bg-gray-50">
              <tr>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col.key)}
                    className="cursor-pointer select-none px-4 py-3 font-semibold text-muted hover:text-foreground"
                  >
                    {col.label}
                    {sortKey === col.key && <span className="ml-1">{sortDir === "asc" ? "↑" : "↓"}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr key={row.zone_id} className="border-b border-panel-border last:border-0 hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-foreground">{row.zone_id}</td>
                  <td className="px-4 py-3">
                    <RiskBadge score={row.grid_heat_risk} />
                  </td>
                  <td className="px-4 py-3 text-muted">{row.heat_score.toFixed(1)}</td>
                  <td className="px-4 py-3 text-muted">{row.demand_score.toFixed(1)}</td>
                  <td className="px-4 py-3 text-muted">{row.infra_score.toFixed(1)}</td>
                  <td className="px-4 py-3 text-muted">{row.outage_score.toFixed(1)}</td>
                  <td className="px-4 py-3 text-muted">{row.vuln_score.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
