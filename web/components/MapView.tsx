"use client";

import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { Map as MLMap, MapLayerMouseEvent, StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { MapResponse } from "@/lib/api";
import { riskColor } from "@/lib/format";

/**
 * MapLibre GL JS needs to load its own web worker script (for tile/geometry
 * processing off the main thread). With Next.js/Turbopack, the worker
 * MapLibre tries to auto-load via import.meta.url isn't always bundled and
 * served at the path the browser requests it from - Next's router then
 * falls back to serving the app shell's index HTML for that request
 * (content-type text/html), which the browser refuses to execute as a
 * worker script ("disallowed MIME type"). The worker then fails to
 * initialize, and every render attempt reports "WebGL context was lost" -
 * the map looks permanently blank even though the base style/tiles and
 * paint expressions are entirely correct, because nothing ever gets past
 * worker startup. Pointing workerUrl at the maplibre-gl package's own
 * prebuilt worker bundle, served from the CDN it's published to, sidesteps
 * Next's bundler entirely for this one script.
 */
if (typeof window !== "undefined") {
  maplibregl.setWorkerUrl(`https://unpkg.com/maplibre-gl@${maplibregl.getVersion()}/dist/maplibre-gl-worker.mjs`);
}

/**
 * A minimal inline raster style (CARTO Positron tiles) instead of fetching
 * a full style JSON from basemaps.cartocdn.com. Fetching the remote style
 * document adds a network round-trip before the map can even start
 * rendering - on a slow or filtered connection that round-trip can hang
 * long enough that the map looks permanently blank, since grid/lines
 * layers are only added inside map.on("load"), which never fires without
 * the style. An inline raster style still needs the tile images themselves
 * over the network, but starts requesting them immediately and renders
 * incrementally as tiles arrive, rather than blocking on one more document
 * first.
 */
const LIGHT_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    "carto-light": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors © CARTO",
    },
  },
  layers: [{ id: "carto-light-layer", type: "raster", source: "carto-light" }],
};

const LOAD_TIMEOUT_MS = 8000;

// Three flat bins - matches the legend under the map (< 40 / 40-60 / >= 60).
// Typed loosely (not against maplibre-gl's style-spec expression types)
// since the exact exported type name varies across maplibre-gl versions -
// these are cast at the call site instead.
const BUCKET_FILL: unknown[] = [
  "case",
  ["!", ["has", "grid_heat_risk"]],
  "#d1d5db",
  ["<", ["to-number", ["get", "grid_heat_risk"]], 40],
  "#16a34a",
  ["<", ["to-number", ["get", "grid_heat_risk"]], 60],
  "#f59e0b",
  "#dc2626",
];

// Continuous ramp - shows degree of risk within a bucket, not just which
// bucket a zone falls in. Same three anchor colors as the bucket view so
// the two modes stay visually related, plus a cool low-end anchor at 0.
const GRADIENT_FILL: unknown[] = [
  "case",
  ["!", ["has", "grid_heat_risk"]],
  "#d1d5db",
  [
    "interpolate",
    ["linear"],
    ["to-number", ["get", "grid_heat_risk"]],
    0,
    "#1d4ed8",
    40,
    "#16a34a",
    60,
    "#f59e0b",
    100,
    "#dc2626",
  ],
];

type StyleMode = "bucket" | "gradient";

export function MapView({
  data,
  onSelectZone,
}: {
  data: MapResponse;
  onSelectZone?: (zoneId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MLMap | null>(null);
  const onSelectZoneRef = useRef(onSelectZone);
  onSelectZoneRef.current = onSelectZone;
  const [status, setStatus] = useState<"loading" | "ready" | "timeout" | "error" | "unsupported">(
    "loading",
  );
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [styleMode, setStyleMode] = useState<StyleMode>("bucket");

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    let loaded = false;
    const timeoutId = window.setTimeout(() => {
      if (!loaded) setStatus("timeout");
    }, LOAD_TIMEOUT_MS);

    // maplibre-gl v6 dropped WebGL1 and requires WebGL2. In an environment
    // with no usable WebGL2 context (some embedded webviews, remote-
    // desktop sessions, GPU access blocked by policy, software-rendering-
    // only setups), v6 reports that as a GPUInitializationError through
    // the "error" event below rather than throwing from the constructor -
    // the try/catch here is just a second line of defense in case
    // construction itself throws for some other reason. Either way, the
    // point is the same: never leave the "loading" overlay spinning
    // forever with the container silently blank - always land on a
    // status the UI actually renders something for.
    let map: MLMap;
    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: LIGHT_STYLE,
        center: computeCenter(data.grid),
        zoom: 10,
        attributionControl: { compact: true },
      });
    } catch (e) {
      // A genuine synchronous constructor failure, not an async callback -
      // there is no later "external system" event to hook this update to,
      // so the lint rule's usual concern (missing a subscription pattern)
      // doesn't apply here.
      window.clearTimeout(timeoutId);
      console.error("MapLibre failed to initialize:", e);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setErrorDetail(e instanceof Error ? e.message : String(e));
      setStatus("error");
      return;
    }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    map.on("error", (e) => {
      console.error("MapLibre error:", e.error);
      const message = e.error?.message ?? "";
      setErrorDetail(message || null);
      // maplibre-gl v6 requires WebGL2; environments without a usable
      // WebGL2 context surface that here as an error event rather than a
      // thrown exception. Detect by message rather than an instanceof
      // check against a specific error class, since the exact exported
      // class name/shape has moved between maplibre-gl versions.
      setStatus(/webgl/i.test(message) ? "unsupported" : "error");
    });

    map.on("load", () => {
      loaded = true;
      window.clearTimeout(timeoutId);
      setStatus("ready");

      map.addSource("grid", { type: "geojson", data: data.grid });
      map.addLayer({
        id: "grid-fill",
        type: "fill",
        source: "grid",
        paint: {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          "fill-color": BUCKET_FILL as any,
          "fill-opacity": 0.55,
        },
      });
      map.addLayer({
        id: "grid-outline",
        type: "line",
        source: "grid",
        paint: { "line-color": "#4b5563", "line-width": 1.2 },
      });

      map.addSource("lines", { type: "geojson", data: data.lines });
      map.addLayer({
        id: "transmission-lines",
        type: "line",
        source: "lines",
        paint: { "line-color": "#14181f", "line-width": 2 },
      });

      const bounds = computeBounds(data.grid);
      if (bounds) {
        map.fitBounds(bounds, { padding: 40, duration: 0 });
      }

      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
      map.on("mousemove", "grid-fill", (e: MapLayerMouseEvent) => {
        map.getCanvas().style.cursor = "pointer";
        const feature = e.features?.[0];
        if (!feature) return;
        const zoneId = feature.properties?.zone_id;
        const risk = feature.properties?.grid_heat_risk;
        const tempF = feature.properties?.heat_raw_f;
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<div style="font-family:sans-serif;font-size:12px;color:${riskColor(risk ?? 0)}">
              <strong>${zoneId}</strong><br/>
              Risk: ${risk != null ? Number(risk).toFixed(1) : "—"}
              ${tempF != null ? `<br/>🌡️ ${Number(tempF).toFixed(1)}°F` : ""}
            </div>`,
          )
          .addTo(map);
      });
      map.on("mouseleave", "grid-fill", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
      map.on("click", "grid-fill", (e: MapLayerMouseEvent) => {
        const zoneId = e.features?.[0]?.properties?.zone_id;
        if (zoneId) onSelectZoneRef.current?.(zoneId);
      });
    });

    return () => {
      window.clearTimeout(timeoutId);
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Swap the fill-color expression in place when the toggle changes -
  // no need to re-add the source/layers, just repaint.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || status !== "ready") return;
    map.setPaintProperty(
      "grid-fill",
      "fill-color",
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (styleMode === "gradient" ? GRADIENT_FILL : BUCKET_FILL) as any,
    );
  }, [styleMode, status]);

  return (
    <div className="relative min-h-0 w-full flex-1 overflow-hidden rounded-xl">
      <div ref={containerRef} className="h-full w-full" />

      {status === "ready" && (
        <div className="absolute left-3 top-3 z-10 flex overflow-hidden rounded-lg border border-panel-border bg-white text-xs shadow-sm">
          <button
            onClick={() => setStyleMode("bucket")}
            className={`px-3 py-1.5 font-medium transition-colors ${
              styleMode === "bucket" ? "bg-brand text-white" : "text-muted hover:bg-gray-50"
            }`}
          >
            Bins
          </button>
          <button
            onClick={() => setStyleMode("gradient")}
            className={`px-3 py-1.5 font-medium transition-colors ${
              styleMode === "gradient" ? "bg-brand text-white" : "text-muted hover:bg-gray-50"
            }`}
          >
            Gradient
          </button>
        </div>
      )}

      {status === "ready" && styleMode === "gradient" && (
        <div className="absolute bottom-3 left-3 z-10 rounded-lg border border-panel-border bg-white px-3 py-2 text-xs text-muted shadow-sm">
          <div
            className="h-2 w-40 rounded-full"
            style={{
              background: "linear-gradient(to right, #1d4ed8, #16a34a, #f59e0b, #dc2626)",
            }}
          />
          <div className="mt-1 flex justify-between">
            <span>0</span>
            <span>Risk score</span>
            <span>100</span>
          </div>
        </div>
      )}

      {status === "loading" && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-white/70 text-sm text-muted">
          Loading map tiles...
        </div>
      )}
      {(status === "timeout" || status === "error" || status === "unsupported") && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1 bg-white/90 px-6 text-center text-sm text-muted">
          <span>
            {status === "timeout" &&
              "Map tiles are taking longer than expected to load — check your network connection or try refreshing."}
            {status === "error" && "Couldn't load the map. Check your network connection or try refreshing."}
            {status === "unsupported" &&
              "This browser/environment doesn't support WebGL, which the map needs to render."}
          </span>
          {errorDetail && <span className="text-xs text-muted/70">{errorDetail}</span>}
        </div>
      )}
    </div>
  );
}

function computeBounds(fc: GeoJSON.FeatureCollection): [[number, number], [number, number]] | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  const visitRing = (ring: GeoJSON.Position[]) => {
    for (const [x, y] of ring) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  };

  for (const feature of fc.features) {
    const geom = feature.geometry;
    if (geom.type === "Polygon") {
      for (const ring of geom.coordinates) visitRing(ring);
    } else if (geom.type === "MultiPolygon") {
      for (const polygon of geom.coordinates) {
        for (const ring of polygon) visitRing(ring);
      }
    }
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return null;
  }
  return [
    [minX, minY],
    [maxX, maxY],
  ];
}

function computeCenter(fc: GeoJSON.FeatureCollection): [number, number] {
  let sumX = 0;
  let sumY = 0;
  let n = 0;
  for (const feature of fc.features) {
    const geom = feature.geometry;
    if (geom.type === "Polygon") {
      for (const ring of geom.coordinates) {
        for (const [x, y] of ring) {
          sumX += x;
          sumY += y;
          n += 1;
        }
      }
    } else if (geom.type === "MultiPolygon") {
      for (const polygon of geom.coordinates) {
        for (const ring of polygon) {
          for (const [x, y] of ring) {
            sumX += x;
            sumY += y;
            n += 1;
          }
        }
      }
    }
  }
  if (n === 0) return [-95.3698, 29.7604]; // downtown Houston fallback
  return [sumX / n, sumY / n];
}
