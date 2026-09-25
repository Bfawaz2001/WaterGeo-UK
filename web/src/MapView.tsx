import { useEffect, useRef, useState } from "react";
import type { GeoJSON } from "geojson";
import {
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  type GeoJSONSource,
  type MapMouseEvent,
  setWorkerUrl,
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
  PointGeometry,
} from "./types";
import type { ViewportQuery } from "./useNearby";

setWorkerUrl(workerUrl);

const SOURCE_LAYERS = {
  hydrology: "watergeo-hydrology",
  "water-quality": "watergeo-water-quality",
  reservoirs: "watergeo-reservoirs",
} as const;

interface Props {
  initial: { longitude: number; latitude: number; zoom: number };
  activeLayers: Set<LayerId>;
  hydrology: HydrologyStation[];
  waterQuality: SamplingPoint[];
  reservoirs: Reservoir[];
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
    if (!map.getSource(source)) map.addSource(source, { type: "geojson", data: pointCollection([], kind as LayerId) });
    if (!map.getLayer(source)) {
      const colors: Record<string, string> = {
        hydrology: "#176b87",
        "water-quality": "#7253a3",
        reservoirs: "#be5a36",
      };
      map.addLayer({
        id: source,
        source,
        type: "circle",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 4, 12, 8],
          "circle-color": colors[kind] ?? "#183c46",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.9,
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
      paint: { "fill-color": "#167d6b", "fill-opacity": 0.24 },
    });
    map.addLayer({
      id: "watergeo-area-line",
      source: "watergeo-area",
      type: "line",
      paint: { "line-color": "#0a584c", "line-width": 2 },
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
      paint: { "fill-color": "#276fba", "fill-opacity": 0.24 },
    });
    map.addLayer({
      id: "watergeo-water-body-line",
      source: "watergeo-water-body",
      type: "line",
      paint: { "line-color": "#174d83", "line-width": 2.5 },
    });
  }
}

export function MapView({
  initial,
  activeLayers,
  hydrology,
  waterQuality,
  reservoirs,
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
      const layerIds = Object.values(SOURCE_LAYERS).filter((layer) => map.getLayer(layer));
      const feature = map.queryRenderedFeatures(event.point, { layers: layerIds })[0];
      const kind = feature?.properties.kind as LayerId | undefined;
      const identity = feature?.properties.identity as string | undefined;
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
    setData(map, "watergeo-area", area ?? { type: "FeatureCollection", features: [] });
    setData(map, "watergeo-water-body", waterBody ?? { type: "FeatureCollection", features: [] });
    for (const [kind, layer] of Object.entries(SOURCE_LAYERS)) {
      map.setLayoutProperty(layer, "visibility", activeLayers.has(kind as LayerId) ? "visible" : "none");
    }
  }, [activeLayers, area, hydrology, reservoirs, styleRevision, waterBody, waterQuality]);

  return (
    <div className="map-region" aria-label="Interactive map workspace">
      <div ref={container} className="map-canvas" data-testid="map-canvas" />
      {mapMessage && <p className="map-message" role="status">{mapMessage}</p>}
      <p className="map-instruction">
        Pan or zoom to refresh enabled point layers. Enable water supply, then click the map to
        inspect the dated boundary snapshot.
      </p>
    </div>
  );
}
