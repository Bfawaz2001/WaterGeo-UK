import { useEffect, useRef, useState } from "react";
import type { GeoJSON } from "geojson";
import {
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  type GeoJSONSource,
  type MapMouseEvent,
  setWorkerUrl,
  addProtocol,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

import { FALLBACK_STYLE, basemapStyle } from "./config";
import type {
  AreaFeature,
  GeoJSONFeatureCollection,
  HydrologyStation,
  LayerId,
  Reservoir,
  SamplingPoint,
  ThamesDischargeSite,
  PointGeometry,
} from "./types";
import type { ViewportQuery } from "./useNearby";
import { Protocol } from "pmtiles";
import type { Overview } from "./overview";

setWorkerUrl(workerUrl);
const tileProtocol = new Protocol();
addProtocol("pmtiles", tileProtocol.tile);

const SOURCE_LAYERS = {
  hydrology: "watergeo-hydrology",
  "water-quality": "watergeo-water-quality",
  reservoirs: "watergeo-reservoirs",
  "thames-discharge": "watergeo-thames-discharge",
} as const;

interface Props {
  overview?: Overview | null;
  focus?: { key: string; longitude?: number; latitude?: number } | null;
  initial: { longitude: number; latitude: number; zoom: number };
  activeLayers: Set<LayerId>;
  hydrology: HydrologyStation[];
  waterQuality: SamplingPoint[];
  reservoirs: Reservoir[];
  thamesDischarge?: ThamesDischargeSite[];
  area: AreaFeature | null;
  waterBody: GeoJSONFeatureCollection | null;
  onViewport: (viewport: ViewportQuery & { zoom: number }) => void;
  onMapClick: (longitude: number, latitude: number) => void;
  onSelectPoint: (layer: LayerId, identity: string) => void;
}

interface PointItem {
  geometry: PointGeometry | null;
  id: string;
  label: string;
}

function pointCollection(items: PointItem[], kind: LayerId): GeoJSON {
  return {
    type: "FeatureCollection",
    features: items.flatMap((item) =>
      item.geometry
        ? [{
        type: "Feature",
        geometry: item.geometry,
        properties: { identity: item.id, label: item.label, kind },
          } as const]
        : [],
    ),
  };
}

function distanceMetres(a: [number, number], b: [number, number]): number {
  const radians = Math.PI / 180;
  const dLat = (b[1] - a[1]) * radians;
  const dLon = (b[0] - a[0]) * radians;
  const lat1 = a[1] * radians;
  const lat2 = b[1] * radians;
  const value =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 6_371_000 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
}

function setData(map: MapLibreMap, source: string, data: GeoJSON): void {
  const geoJsonSource = map.getSource<GeoJSONSource>(source);
  if (geoJsonSource) void geoJsonSource.setData(data);
}

function addExplorerSources(map: MapLibreMap): void {
  for (const [kind, source] of Object.entries(SOURCE_LAYERS)) {
    if (!map.getSource(source)) map.addSource(source, {
      type: "geojson",
      data: pointCollection([], kind as LayerId),
      cluster: true,
      clusterMaxZoom: 10,
      clusterRadius: 44,
    });
    const colors: Record<string, string> = {
      hydrology: "#007f8b",
      "water-quality": "#6c55a3",
      reservoirs: "#c4682f",
      "thames-discharge": "#c23857",
    };
    const color = colors[kind] ?? "#183c46";
    if (!map.getLayer(`${source}-clusters`)) {
      map.addLayer({
        id: `${source}-clusters`,
        source,
        type: "circle",
        filter: ["has", "point_count"],
        paint: {
          "circle-radius": ["step", ["get", "point_count"], 17, 20, 21, 60, 26],
          "circle-color": color,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 3,
          "circle-opacity": 0.94,
        },
      });
      map.addLayer({
        id: `${source}-cluster-count`,
        source,
        type: "symbol",
        filter: ["has", "point_count"],
        layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
        paint: { "text-color": "#ffffff" },
      });
    }
    if (!map.getLayer(source)) {
      map.addLayer({
        id: source,
        source,
        type: "circle",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 5, 12, 8.5],
          "circle-color": color,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
          "circle-opacity": 0.96,
        },
      });
    }
  }
  if (!map.getSource("watergeo-area")) {
    map.addSource("watergeo-area", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: "watergeo-area-fill",
      source: "watergeo-area",
      type: "fill",
      paint: { "fill-color": "#11806f", "fill-opacity": 0.2 },
    });
    map.addLayer({
      id: "watergeo-area-line",
      source: "watergeo-area",
      type: "line",
      paint: { "line-color": "#075c51", "line-width": 3 },
    });
  }
  if (!map.getSource("watergeo-water-body")) {
    map.addSource("watergeo-water-body", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: "watergeo-water-body-fill",
      source: "watergeo-water-body",
      type: "fill",
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": "#2578b8", "fill-opacity": 0.2 },
    });
    map.addLayer({
      id: "watergeo-water-body-line",
      source: "watergeo-water-body",
      type: "line",
      paint: { "line-color": "#174d83", "line-width": 2.5 },
    });
  }
  if (!map.getSource("watergeo-selection")) {
    map.addSource("watergeo-selection", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: "watergeo-selection-halo",
      source: "watergeo-selection",
      type: "circle",
      paint: { "circle-radius": 14, "circle-color": "#ffffff", "circle-opacity": 0.88, "circle-stroke-color": "#073f47", "circle-stroke-width": 3 },
    });
    map.addLayer({
      id: "watergeo-selection-core",
      source: "watergeo-selection",
      type: "circle",
      paint: { "circle-radius": 5, "circle-color": "#f2a63b", "circle-stroke-color": "#073f47", "circle-stroke-width": 1.5 },
    });
  }
}

export function MapView({
  overview,
  focus,
  initial,
  activeLayers,
  hydrology,
  waterQuality,
  reservoirs,
  thamesDischarge = [],
  area,
  waterBody,
  onViewport,
  onMapClick,
  onSelectPoint,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | undefined>(undefined);
  const callbacks = useRef({ onViewport, onMapClick, onSelectPoint, activeLayers });
  const [mapMessage, setMapMessage] = useState<string>();
  const [styleRevision, setStyleRevision] = useState(0);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    if (map.getLayer("watergeo-overview")) map.removeLayer("watergeo-overview");
    if (map.getSource("watergeo-overview")) map.removeSource("watergeo-overview");
    if (overview) {
      map.addSource("watergeo-overview", { type: "vector", url: `pmtiles://${window.location.origin}${overview.url}`, attribution: overview.attribution });
      map.addLayer({ id: "watergeo-overview", type: "line", source: "watergeo-overview", "source-layer": "water_supply", filter: ["==", ["get", "snapshot_id"], overview.snapshot], paint: { "line-color": "#167d6b", "line-width": 1, "line-opacity": 0.6 } });
    }
  }, [overview, styleRevision]);

  useEffect(() => {
    callbacks.current = { onViewport, onMapClick, onSelectPoint, activeLayers };
  }, [activeLayers, onMapClick, onSelectPoint, onViewport]);

  useEffect(() => {
    if (!container.current) return;
    const configuredStyle = basemapStyle();
    let fallbackApplied = configuredStyle === FALLBACK_STYLE;
    let disposed = false;
    const map = new MapLibreMap({
      container: container.current,
      style: configuredStyle,
      center: [initial.longitude, initial.latitude],
      zoom: initial.zoom,
      minZoom: 3,
      maxZoom: 17,
      attributionControl: { compact: false },
    });
    mapRef.current = map;
    const resize = new ResizeObserver(() => map.resize());
    resize.observe(container.current);
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric" }), "bottom-right");

    const publishViewport = () => {
      const center = map.getCenter();
      const northEast = map.getBounds().getNorthEast();
      callbacks.current.onViewport({
        longitude: center.lng,
        latitude: center.lat,
        zoom: map.getZoom(),
        radiusM: Math.max(
          1_000,
          distanceMetres([center.lng, center.lat], [northEast.lng, northEast.lat]),
        ),
      });
    };
    const loaded = () => {
      addExplorerSources(map);
      setStyleRevision((revision) => revision + 1);
      publishViewport();
    };
    const clicked = (event: MapMouseEvent) => {
      const pointLayers = Object.values(SOURCE_LAYERS).filter((layer) => map.getLayer(layer));
      const clusterLayers = Object.values(SOURCE_LAYERS)
        .map((layer) => `${layer}-clusters`)
        .filter((layer) => map.getLayer(layer));
      const layerIds = [...pointLayers, ...clusterLayers];
      const feature = map.queryRenderedFeatures(event.point, { layers: layerIds })[0];
      if (!feature) {
        if (callbacks.current.activeLayers.has("water-supply")) {
          callbacks.current.onMapClick(event.lngLat.lng, event.lngLat.lat);
        }
        return;
      }
      const clusterId = feature.properties.cluster_id as number | undefined;
      if (clusterId !== undefined && feature.geometry.type === "Point") {
        const source = map.getSource<GeoJSONSource>(feature.source);
        const center = feature.geometry.coordinates as [number, number];
        if (source) {
          void source.getClusterExpansionZoom(clusterId).then((zoom) => {
            map.easeTo({ center, zoom });
          });
        }
        return;
      }
      const kind = feature.properties.kind as LayerId | undefined;
      const identity = feature.properties.identity as string | undefined;
      if (kind && identity) callbacks.current.onSelectPoint(kind, identity);
      else if (callbacks.current.activeLayers.has("water-supply")) {
        callbacks.current.onMapClick(event.lngLat.lng, event.lngLat.lat);
      }
    };
    const restoreFallback = () => {
      if (disposed) return;
      addExplorerSources(map);
      setStyleRevision((revision) => revision + 1);
    };
    const handleError = () => {
      if (fallbackApplied) return;
      fallbackApplied = true;
      setMapMessage("Basemap unavailable. WaterGeo layers remain usable without it.");
      map.once("style.load", restoreFallback);
      map.setStyle(FALLBACK_STYLE);
    };
    map.on("load", loaded);
    map.on("moveend", publishViewport);
    map.on("click", clicked);
    map.on("error", handleError);
    return () => {
      disposed = true;
      resize.disconnect();
      map.off("load", loaded);
      map.off("moveend", publishViewport);
      map.off("click", clicked);
      map.off("error", handleError);
      map.off("style.load", restoreFallback);
      map.remove();
      mapRef.current = undefined;
    };
  }, [initial.latitude, initial.longitude, initial.zoom]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    addExplorerSources(map);
    setData(
      map,
      SOURCE_LAYERS.hydrology,
      pointCollection(
        hydrology.map((item) => ({
          geometry: item.geometry,
          id: item.station_id,
          label: item.labels[0] ?? item.station_id,
        })),
        "hydrology",
      ),
    );
    setData(
      map,
      SOURCE_LAYERS["water-quality"],
      pointCollection(
        waterQuality.map((item) => ({
          geometry: item.geometry,
          id: item.sampling_point_id,
          label: item.pref_label ?? item.alt_label,
        })),
        "water-quality",
      ),
    );
    setData(
      map,
      SOURCE_LAYERS.reservoirs,
      pointCollection(
        reservoirs.map((item) => ({ geometry: item.geometry, id: item.reservoir_id, label: item.name })),
        "reservoirs",
      ),
    );
    setData(
      map,
      SOURCE_LAYERS["thames-discharge"],
      pointCollection(
        thamesDischarge.map((item) => ({
          geometry: item.geometry,
          id: item.site_id,
          label: `${item.location_name}: ${item.alert_status}`,
        })),
        "thames-discharge",
      ),
    );
    setData(map, "watergeo-area", area ?? { type: "FeatureCollection", features: [] });
    setData(map, "watergeo-water-body", waterBody ?? { type: "FeatureCollection", features: [] });
    for (const [kind, layer] of Object.entries(SOURCE_LAYERS)) {
      const visibility = activeLayers.has(kind as LayerId) ? "visible" : "none";
      map.setLayoutProperty(layer, "visibility", visibility);
      map.setLayoutProperty(`${layer}-clusters`, "visibility", visibility);
      map.setLayoutProperty(`${layer}-cluster-count`, "visibility", visibility);
    }
  }, [activeLayers, area, hydrology, reservoirs, styleRevision, thamesDischarge, waterBody, waterQuality]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    if (!focus) {
      setData(map, "watergeo-selection", { type: "FeatureCollection", features: [] });
      return;
    }
    if (focus.longitude !== undefined && focus.latitude !== undefined) {
      setData(map, "watergeo-selection", {
        type: "FeatureCollection",
        features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [focus.longitude, focus.latitude] } }],
      });
      map.easeTo({ center: [focus.longitude, focus.latitude], zoom: Math.max(map.getZoom(), 11) });
      return;
    }
    setData(map, "watergeo-selection", { type: "FeatureCollection", features: [] });
    const bounds = { west: 180, south: 90, east: -180, north: -90, found: false };
    const inspect = (value: unknown) => {
      if (!Array.isArray(value)) return;
      if (value.length >= 2 && typeof value[0] === "number" && typeof value[1] === "number") {
        bounds.west = Math.min(bounds.west, value[0]);
        bounds.east = Math.max(bounds.east, value[0]);
        bounds.south = Math.min(bounds.south, value[1]);
        bounds.north = Math.max(bounds.north, value[1]);
        bounds.found = true;
        return;
      }
      for (const child of value) inspect(child);
    };
    if (area) inspect(area.geometry.coordinates);
    if (waterBody) for (const feature of waterBody.features) {
      if ("coordinates" in feature.geometry) inspect(feature.geometry.coordinates);
      else for (const geometry of feature.geometry.geometries) {
        if ("coordinates" in geometry) inspect(geometry.coordinates);
      }
    }
    if (bounds.found) {
      map.fitBounds([[bounds.west, bounds.south], [bounds.east, bounds.north]], {
        padding: 64,
        maxZoom: 12,
      });
    }
  }, [area, focus, styleRevision, waterBody]);

  return (
    <div className="map-region" aria-label="Interactive map workspace">
      <div ref={container} className="map-canvas" data-testid="map-canvas" />
      {mapMessage && <p className="map-message" role="status">{mapMessage}</p>}
      <p className="map-instruction">
        Move the map to refresh nearby results. Water-supply lookup runs only when its layer is enabled.
      </p>
    </div>
  );
}
