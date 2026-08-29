"use client";

import { useEffect, useState } from "react";

import { api, MapResponse, MetaResponse } from "@/lib/api";
import { MapView } from "@/components/MapView";
import { MockDataBanner } from "@/components/MockDataBanner";
import { Spinner, ErrorPanel } from "@/components/Feedback";

export default function MapPage() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [mapData, setMapData] = useState<MapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getMeta(), api.getMapData()])
      .then(([m, d]) => {
        setMeta(m);
        setMapData(d);
      })
      .catch((e) => setError(e.message ?? "Unknown error"));
  }, []);

  if (error) return <ErrorPanel message={error} />;
  if (!mapData || !meta) return <Spinner label="Loading map data..." />;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 shrink-0">
        <h1 className="text-2xl font-semibold text-foreground">Map View</h1>
        <p className="mt-1 text-sm text-muted">
          Grid heat risk by zone, with nearby transmission infrastructure.
        </p>
      </div>

      {meta.using_mock_data && (
        <div className="shrink-0">
          <MockDataBanner />
        </div>
      )}

      <div className="panel flex min-h-0 flex-1 flex-col p-3">
        <MapView data={mapData} />
      </div>

      <div className="mt-3 flex shrink-0 flex-wrap items-center gap-6 text-xs text-muted">
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

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
