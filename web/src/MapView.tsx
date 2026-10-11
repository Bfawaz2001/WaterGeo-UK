import { useEffect, useRef, useState } from "react";
import type { GeoJSON } from "geojson";
import {
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  type GeoJSONSource,
  type ExpressionSpecification,
  type MapMouseEvent,
  setWorkerUrl,
  addProtocol,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

import { geometryBounds, type MapNavigation } from "./mapNavigation";
import { FLOOD_STATES } from "./floodFilters";
import { FALLBACK_STYLE, basemapStyle } from "./config";
import type {
  AreaFeature,
  BathingWater,
  FloodArea,
  GeoJSONFeatureCollection,
  HydrologyStation,
  RainfallStation,
  LayerId,
  Reservoir,
  SamplingPoint,
  ThamesDischargeSite,
  PointGeometry,
  WaterCompanyFeatureCollection,
} from "./types";
import type { ViewportQuery } from "./useNearby";
import { Protocol } from "pmtiles";
import type { Overview } from "./overview";

const FLOOD_COLOR: ExpressionSpecification = [
  "match", ["get", "severity_level"],
  1, FLOOD_STATES[0].color, 2, FLOOD_STATES[1].color,
  3, FLOOD_STATES[2].color, FLOOD_STATES[3].color,
];

setWorkerUrl(workerUrl);
const tileProtocol = new Protocol();
addProtocol("pmtiles", tileProtocol.tile);

const SOURCE_LAYERS = {
  hydrology: "watergeo-hydrology",
  rainfall: "watergeo-rainfall",
  "water-quality": "watergeo-water-quality",
  "bathing-waters": "watergeo-bathing-waters",
  reservoirs: "watergeo-reservoirs",
  "thames-discharge": "watergeo-thames-discharge",
} as const;

interface Props {
  navigation?: MapNavigation | null;
  overview?: Overview | null;
  focus?: { key: string; longitude?: number; latitude?: number } | null;
  initial: { longitude: number; latitude: number; zoom: number };
  activeLayers: Set<LayerId>;
  hydrology: HydrologyStation[];
  rainfall?: RainfallStation[];
  bathingWaters?: BathingWater[];
  floodWarnings?: FloodArea[];
  waterQuality: SamplingPoint[];
  reservoirs: Reservoir[];
  thamesDischarge?: ThamesDischargeSite[];
  area: AreaFeature | null;
  companyAreas?: WaterCompanyFeatureCollection | null;
  waterBody: GeoJSONFeatureCollection | null;
  onViewport: (viewport: ViewportQuery & { zoom: number }) => void;
  onMapClick: (longitude: number, latitude: number) => void;
  onSelectPoint: (layer: LayerId, identity: string) => void;
}

interface PointItem {
  geometry: PointGeometry | null;
  id: string;
  label: string;
  classification?: string | null;
}

function pointCollection(items: PointItem[], kind: LayerId): GeoJSON {
  return {
    type: "FeatureCollection",
    features: items.flatMap((item) =>
      item.geometry
        ? [{
        type: "Feature",
        geometry: item.geometry,
        properties: { identity: item.id, label: item.label, kind, classification: item.classification },
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
      rainfall: "#2766aa",
      "water-quality": "#6c55a3",
      "bathing-waters": "#00a3b8",
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
        layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12, "text-font": ["Noto Sans Regular"] },
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
          "circle-color": kind === "bathing-waters" ? [
            "match", ["get", "classification"],
            "Excellent", "#087566", "Good", "#2477a8", "Sufficient", "#b17918",
            "Poor", "#b53b4b", "#68777a",
          ] : color,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
          "circle-opacity": 0.96,
        },
      });
    }
  }
  if (!map.getSource("watergeo-flood-warnings")) {
    map.addSource("watergeo-flood-warnings", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: "watergeo-flood-warnings-fill",
      source: "watergeo-flood-warnings",
      type: "fill",
      paint: { "fill-color": FLOOD_COLOR, "fill-opacity": 0.22 },
    });
    map.addLayer({
      id: "watergeo-flood-warnings-line",
      source: "watergeo-flood-warnings",
      type: "line",
      paint: { "line-color": FLOOD_COLOR, "line-width": 2 },
    });
  }
  if (!map.getSource("watergeo-area")) {
    map.addSource("watergeo-company-areas", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: "watergeo-company-areas-fill",
      source: "watergeo-company-areas",
      type: "fill",
      paint: { "fill-color": "#2f8f80", "fill-opacity": 0.12 },
    });
    map.addLayer({
      id: "watergeo-company-areas-line",
      source: "watergeo-company-areas",
      type: "line",
      paint: { "line-color": "#26766b", "line-width": 1.4, "line-opacity": 0.8 },
    });
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
  navigation,
  focus,
  initial,
  activeLayers,
  hydrology,
  rainfall = [],
  bathingWaters = [],
  floodWarnings = [],
  waterQuality,
  reservoirs,
  thamesDischarge = [],
  area,
  companyAreas = null,
  waterBody,
  onViewport,
  onMapClick,
  onSelectPoint,
}: Props) {
  const lastNavigation = useRef<number | undefined>(undefined);
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | undefined>(undefined);
  const callbacks = useRef({ onViewport, onMapClick, onSelectPoint, activeLayers });
  const [mapMessage, setMapMessage] = useState<string>();
  const [styleRevision, setStyleRevision] = useState(0);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("watergeo-selection")) return;
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
      const floodLayers = map.getLayer("watergeo-flood-warnings-fill")
        ? ["watergeo-flood-warnings-fill"]
        : [];
      const layerIds = [...pointLayers, ...clusterLayers, ...floodLayers];
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
            map.easeTo({ center, zoom, duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 500 });
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
    if (!map?.getSource("watergeo-selection")) return;
    addExplorerSources(map);
    setData(
      map,
      SOURCE_LAYERS.rainfall,
      pointCollection(
        rainfall.map((item) => ({
          geometry:
            item.longitude === null || item.latitude === null
              ? null
              : { type: "Point", coordinates: [item.longitude, item.latitude] },
          id: item.station_id,
          label: item.display_name ?? `Rainfall gauge ${item.station_id}`,
        })),
        "rainfall",
      ),
    );
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
      SOURCE_LAYERS["bathing-waters"],
      pointCollection(
        bathingWaters.map((item) => ({
          geometry: { type: "Point", coordinates: [item.longitude, item.latitude] },
          id: item.bathing_water_id,
          label: item.name,
          classification: item.classification,
        })),
        "bathing-waters",
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
    setData(map, "watergeo-company-areas", companyAreas ?? { type: "FeatureCollection", features: [] });
    setData(map, "watergeo-flood-warnings", {
      type: "FeatureCollection",
      features: floodWarnings.map((item) => ({
        type: "Feature",
        id: item.area_id,
        geometry: item.geometry,
        properties: { identity: item.area_id, label: item.label, kind: "flood-warnings", severity_level: item.severity_level },
      })),
    });
    const floodVisibility = activeLayers.has("flood-warnings") ? "visible" : "none";
    map.setLayoutProperty("watergeo-flood-warnings-fill", "visibility", floodVisibility);
    map.setLayoutProperty("watergeo-flood-warnings-line", "visibility", floodVisibility);
    setData(map, "watergeo-water-body", waterBody ?? { type: "FeatureCollection", features: [] });
    for (const [kind, layer] of Object.entries(SOURCE_LAYERS)) {
      const visibility = activeLayers.has(kind as LayerId) ? "visible" : "none";
      map.setLayoutProperty(layer, "visibility", visibility);
      map.setLayoutProperty(`${layer}-clusters`, "visibility", visibility);
      map.setLayoutProperty(`${layer}-cluster-count`, "visibility", visibility);
    }
  }, [activeLayers, area, bathingWaters, companyAreas, floodWarnings, hydrology, rainfall, reservoirs, styleRevision, thamesDischarge, waterBody, waterQuality]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("watergeo-selection")) return;
    if (!focus) {
      setData(map, "watergeo-selection", { type: "FeatureCollection", features: [] });
      return;
    }
    if (focus.longitude !== undefined && focus.latitude !== undefined) {
      setData(map, "watergeo-selection", {
        type: "FeatureCollection",
        features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [focus.longitude, focus.latitude] } }],
      });
      map.easeTo({ center: [focus.longitude, focus.latitude], zoom: Math.max(map.getZoom(), 11), duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 500 });
      return;
    }
    setData(map, "watergeo-selection", { type: "FeatureCollection", features: [] });
    const bounds = geometryBounds([
      ...(area ? [area.geometry] : []),
      ...(waterBody?.features.map((feature) => feature.geometry) ?? []),
    ]);
    if (bounds) map.fitBounds(bounds, { padding: 64, maxZoom: 12, duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 500 });
  }, [area, focus, styleRevision, waterBody]);

  useEffect(() => {
    const map = mapRef.current;
    // Source installation marks initial style readiness. Updating GeoJSON tiles can
    // temporarily make isStyleLoaded false without preventing a camera movement.
    if (!map?.getSource("watergeo-selection") || !navigation || lastNavigation.current === navigation.id) return;
    lastNavigation.current = navigation.id;
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 650;
    const [southWest, northEast] = navigation.bounds;
    if (southWest[0] === northEast[0] && southWest[1] === northEast[1]) {
      map.easeTo({ center: southWest, zoom: Math.min(navigation.maxZoom ?? 12, 12), duration });
    } else {
      map.fitBounds(navigation.bounds, { padding: window.innerWidth > 1100 ? { top: 64, bottom: 64, left: 48, right: 360 } : 48, maxZoom: navigation.maxZoom ?? 12, duration });
    }
  }, [navigation, styleRevision]);

  return (
    <div className="map-region" aria-label="Interactive map workspace">
      <div ref={container} className="map-canvas" data-testid="map-canvas" />
      {mapMessage && <p className="map-message" role="status">{mapMessage}</p>}
      <p className="map-instruction">
        Clusters count loaded results only. Move or zoom to explore nearby features. Water-supply lookup runs only when its layer is enabled.
      </p>
    </div>
  );
}
