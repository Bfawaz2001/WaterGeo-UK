import { act, render } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { AreaFeature, GeoJSONFeatureCollection, WaterCompanyFeatureCollection } from "./types";
import type { Overview } from "./overview";

const mock = vi.hoisted(() => {
  class Map {
    static latest: Map;
    listeners = new globalThis.Map<string, Set<(...args: unknown[]) => void>>();
    sources = new globalThis.Map<string, { setData: ReturnType<typeof vi.fn>; getClusterExpansionZoom?: ReturnType<typeof vi.fn> }>();
    layers = new Set<string>();
    operations: string[] = [];
    loaded = false;
    setLayoutProperty = vi.fn();
    remove = vi.fn(() => this.listeners.clear());
    constructor() { Map.latest = this; }
    on(event: string, callback: (...args: unknown[]) => void) {
      const listeners = this.listeners.get(event) ?? new Set();
      listeners.add(callback);
      this.listeners.set(event, listeners);
    }
    off(event: string, callback: (...args: unknown[]) => void) { this.listeners.get(event)?.delete(callback); }
    once(event: string, callback: () => void) {
      this.operations.push(`once:${event}`);
      const once = () => { this.off(event, once); callback(); };
      this.on(event, once);
    }
    emit(event: string, ...args: unknown[]) { for (const callback of [...this.listeners.get(event) ?? []]) callback(...args); }
    addControl() {}
    resize() {}
    removeLayer(id: string) { this.layers.delete(id); }
    removeSource(id: string) { this.sources.delete(id); }
    getCenter() { return { lng: -1, lat: 52 }; }
    getBounds() { return { getNorthEast: () => ({ lng: 0, lat: 53 }) }; }
    getZoom() { return 8; }
    isStyleLoaded() { return this.loaded; }
    getSource(id: string) { return this.sources.get(id); }
    addSource = vi.fn((id: string) => { this.sources.set(id, { setData: vi.fn(), getClusterExpansionZoom: vi.fn().mockResolvedValue(12) }); });
    queryRenderedFeatures = vi.fn((): Array<Record<string, unknown>> => []);
    easeTo = vi.fn();
    fitBounds = vi.fn();
    getLayer(id: string) { return this.layers.has(id); }
    addLayer = vi.fn((layer: { id: string }) => { this.layers.add(layer.id); });
    setStyle = vi.fn(() => {
      this.operations.push("setStyle");
      this.sources.clear();
      this.layers.clear();
      this.loaded = false;
    });
  }
  return { Map };
});
vi.mock("maplibre-gl", () => ({
  Map: mock.Map, NavigationControl: class {}, ScaleControl: class {}, setWorkerUrl: vi.fn(), addProtocol: vi.fn(),
}));
vi.mock("maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url", () => ({ default: "mock-worker" }));

import { MapView } from "./MapView";

beforeEach(() => { window.matchMedia = vi.fn().mockReturnValue({ matches: false }); });

function renderMap(overview: Overview | null = null, focus?: { key: string; longitude?: number; latitude?: number }, companyAreas?: WaterCompanyFeatureCollection) {
  const area = { type: "Feature", geometry: { type: "MultiPolygon", coordinates: [] } } as unknown as AreaFeature;
  const waterBody: GeoJSONFeatureCollection = { type: "FeatureCollection", features: [] };
  const { unmount } = render(<MapView
    overview={overview}
    focus={focus ?? null}
    initial={{ longitude: -1, latitude: 52, zoom: 8 }}
    activeLayers={new Set(["water-supply"])}
    hydrology={[]} waterQuality={[]} reservoirs={[]}
    area={area} companyAreas={companyAreas ?? null} waterBody={waterBody}
    onViewport={vi.fn()} onMapClick={vi.fn()} onSelectPoint={vi.fn()}
  />);
  return { area, waterBody, map: mock.Map.latest, unmount };
}

it("draws the company collection beneath the stronger selected-area layers", () => {
  const companyAreas = {
    type: "FeatureCollection", snapshot_id: "snapshot",
    company: { company_acronym: "ANH", display_name: "Anglian Water", publisher_labels: ["Anglian Water"], area_count: 1 },
    features: [],
  } satisfies WaterCompanyFeatureCollection;
  const { map } = renderMap(null, undefined, companyAreas);
  act(() => { map.loaded = true; map.emit("load"); });
  expect(map.getSource("watergeo-company-areas")?.setData).toHaveBeenLastCalledWith(companyAreas);
  const companyLine = map.addLayer.mock.calls.findIndex(([layer]) => layer.id === "watergeo-company-areas-line");
  const selectedFill = map.addLayer.mock.calls.findIndex(([layer]) => layer.id === "watergeo-area-fill");
  expect(companyLine).toBeLessThan(selectedFill);
});

it("restores current data only after the initial and fallback styles fully load", () => {
  const { area, waterBody, map, unmount } = renderMap();
  expect(map.sources.size).toBe(0);
  act(() => { map.loaded = true; map.emit("load"); });
  expect(map.addSource).toHaveBeenCalledWith(
    "watergeo-hydrology",
    expect.objectContaining({ cluster: true, clusterMaxZoom: 10, clusterRadius: 44 }),
  );
  expect(map.getSource("watergeo-area")?.setData).toHaveBeenLastCalledWith(area);
  expect(map.getSource("watergeo-water-body")?.setData).toHaveBeenLastCalledWith(waterBody);
  expect(map.setLayoutProperty).toHaveBeenCalledWith("watergeo-hydrology", "visibility", "none");

  map.operations.length = 0;
  act(() => map.emit("error"));
  expect(map.operations).toEqual(["once:style.load", "setStyle"]);
  expect(map.setStyle).toHaveBeenCalledOnce();
  expect(map.sources.size).toBe(0);
  act(() => map.emit("styledata"));
  expect(map.sources.size).toBe(0);
  act(() => { map.loaded = true; map.emit("style.load"); });
  expect(map.getSource("watergeo-area")?.setData).toHaveBeenLastCalledWith(area);
  expect(map.getSource("watergeo-water-body")?.setData).toHaveBeenLastCalledWith(waterBody);
  expect(map.setLayoutProperty).toHaveBeenCalledWith(
    "watergeo-hydrology", "visibility", "none",
  );
  act(() => map.emit("error"));
  expect(map.setStyle).toHaveBeenCalledOnce();
  expect(map.listeners.get("load")?.size).toBe(1);
  unmount();
  expect(map.remove).toHaveBeenCalledOnce();
  expect(map.listeners.size).toBe(0);
});

it("styles bathing-water points by exact publisher classification", () => {
  const { map } = renderMap();
  act(() => { map.loaded = true; map.emit("load"); });
  expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({
    id: "watergeo-bathing-waters",
    paint: expect.objectContaining({
      "circle-color": [
        "match", ["get", "classification"],
        "Excellent", "#087566", "Good", "#2477a8", "Sufficient", "#b17918",
        "Poor", "#b53b4b", "#68777a",
      ],
    }),
  }));
});

it("renders a source-independent selection halo for a focused point", () => {
  const { map } = renderMap(null, { key: "hydrology:station", longitude: -1.5, latitude: 52.5 });
  act(() => { map.loaded = true; map.emit("load"); });
  expect(map.getSource("watergeo-selection")?.setData).toHaveBeenLastCalledWith({
    type: "FeatureCollection",
    features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [-1.5, 52.5] } }],
  });
  expect(map.easeTo).toHaveBeenCalledWith({ center: [-1.5, 52.5], zoom: 11, duration: 500 });
});

it("installs the PMTiles overview only after load and restores it after fallback", () => {
  const { map } = renderMap({ url: "/exports/snapshot/water-supply.pmtiles", snapshot: "snapshot", attribution: "Ofwat attribution" });
  expect(map.getLayer("watergeo-overview")).toBe(false);
  act(() => { map.loaded = true; map.emit("load"); });
  expect(map.getLayer("watergeo-overview")).toBe(true);
  act(() => map.emit("error"));
  expect(map.getLayer("watergeo-overview")).toBe(false);
  act(() => { map.loaded = true; map.emit("style.load"); });
  expect(map.getLayer("watergeo-overview")).toBe(true);
});

it("expands a point cluster instead of treating it as an individual feature", async () => {
  const { map } = renderMap();
  act(() => { map.loaded = true; map.emit("load"); });
  map.queryRenderedFeatures.mockReturnValueOnce([{
    source: "watergeo-hydrology",
    properties: { cluster_id: 7, point_count: 4 },
    geometry: { type: "Point", coordinates: [-1.5, 52.5] },
  }]);
  act(() => map.emit("click", { point: { x: 10, y: 10 }, lngLat: { lng: -1.5, lat: 52.5 } }));
  await act(async () => Promise.resolve());
  expect(map.getSource("watergeo-hydrology")?.getClusterExpansionZoom).toHaveBeenCalledWith(7);
  expect(map.easeTo).toHaveBeenCalledWith({ center: [-1.5, 52.5], zoom: 12, duration: 500 });
});

it("removes a pending fallback listener and ignores a captured late callback on teardown", () => {
  const { map, unmount } = renderMap();
  act(() => map.emit("error"));
  const lateCallback = [...(map.listeners.get("style.load") ?? [])][0];
  expect(lateCallback).toBeDefined();
  expect(map.setStyle).toHaveBeenCalledOnce();
  const additionsBeforeUnmount = map.addSource.mock.calls.length;

  unmount();
  expect(map.listeners.size).toBe(0);
  act(() => lateCallback?.());
  expect(map.addSource).toHaveBeenCalledTimes(additionsBeforeUnmount);
  expect(map.remove).toHaveBeenCalledOnce();
});


it("navigates once per intent, waits for style load, and respects reduced motion", () => {
  const props = {
    initial: { longitude: -1, latitude: 52, zoom: 8 }, activeLayers: new Set<import("./types").LayerId>(),
    hydrology: [], waterQuality: [], reservoirs: [], area: null, waterBody: null,
    onViewport: vi.fn(), onMapClick: vi.fn(), onSelectPoint: vi.fn(),
  };
  const navigation = { id: 1, bounds: [[-2, 51], [0, 53]] as [[number, number], [number, number]] };
  const { rerender } = render(<MapView {...props} navigation={navigation} />);
  const map = mock.Map.latest;
  expect(map.fitBounds).not.toHaveBeenCalled();
  act(() => { map.loaded = true; map.emit("load"); });
  expect(map.fitBounds).toHaveBeenCalledOnce();
  expect(map.fitBounds).toHaveBeenLastCalledWith(navigation.bounds, expect.objectContaining({ maxZoom: 12, duration: 650 }));
  expect(map.addLayer).toHaveBeenCalledWith(expect.objectContaining({
    id: "watergeo-hydrology-cluster-count", layout: expect.objectContaining({ "text-font": ["Noto Sans Regular"] }),
  }));
  act(() => map.emit("moveend"));
  rerender(<MapView {...props} navigation={{ ...navigation }} hydrology={[]} />);
  expect(map.fitBounds).toHaveBeenCalledOnce();
  act(() => map.emit("error"));
  act(() => { map.loaded = true; map.emit("style.load"); });
  expect(map.fitBounds).toHaveBeenCalledOnce();
  map.loaded = false; // GeoJSON tiles are updating; explicit navigation still works.
  const matchMedia = vi.spyOn(window, "matchMedia").mockReturnValue({ matches: true } as MediaQueryList);
  rerender(<MapView {...props} navigation={{ id: 2, bounds: [[-1, 52], [-1, 52]] }} />);
  expect(map.easeTo).toHaveBeenLastCalledWith({ center: [-1, 52], zoom: 12, duration: 0 });
  matchMedia.mockRestore();
});


it("updates geometry and visibility while previously installed sources are still loading", () => {
  const props = {
    initial: { longitude: -1, latitude: 52, zoom: 8 }, activeLayers: new Set<import("./types").LayerId>(),
    hydrology: [], waterQuality: [], reservoirs: [], area: null, waterBody: null,
    onViewport: vi.fn(), onMapClick: vi.fn(), onSelectPoint: vi.fn(),
  };
  const { rerender } = render(<MapView {...props} />);
  const map = mock.Map.latest;
  act(() => { map.loaded = true; map.emit("load"); });
  map.loaded = false;
  const area: AreaFeature = { type: "Feature", properties: {}, geometry: { type: "MultiPolygon", coordinates: [] } } as unknown as AreaFeature;
  rerender(<MapView {...props} area={area} activeLayers={new Set(["hydrology"])} />);
  expect(map.getSource("watergeo-area")?.setData).toHaveBeenLastCalledWith(area);
  expect(map.setLayoutProperty).toHaveBeenCalledWith("watergeo-hydrology", "visibility", "visible");
});
