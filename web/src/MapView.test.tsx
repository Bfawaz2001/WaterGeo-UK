import { act, render } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { AreaFeature, GeoJSONFeatureCollection } from "./types";

const mock = vi.hoisted(() => {
  class Map {
    static latest: Map;
    listeners = new globalThis.Map<string, Set<() => void>>();
    sources = new globalThis.Map<string, { setData: ReturnType<typeof vi.fn> }>();
    layers = new Set<string>();
    operations: string[] = [];
    loaded = false;
    setLayoutProperty = vi.fn();
    remove = vi.fn(() => this.listeners.clear());
    constructor() { Map.latest = this; }
    on(event: string, callback: () => void) {
      const listeners = this.listeners.get(event) ?? new Set();
      listeners.add(callback);
      this.listeners.set(event, listeners);
    }
    off(event: string, callback: () => void) { this.listeners.get(event)?.delete(callback); }
    once(event: string, callback: () => void) {
      this.operations.push(`once:${event}`);
      const once = () => { this.off(event, once); callback(); };
      this.on(event, once);
    }
    emit(event: string) { for (const callback of [...this.listeners.get(event) ?? []]) callback(); }
    addControl() {}
    getCenter() { return { lng: -1, lat: 52 }; }
    getBounds() { return { getNorthEast: () => ({ lng: 0, lat: 53 }) }; }
    getZoom() { return 8; }
    isStyleLoaded() { return this.loaded; }
    getSource(id: string) { return this.sources.get(id); }
    addSource = vi.fn((id: string) => { this.sources.set(id, { setData: vi.fn() }); });
    getLayer(id: string) { return this.layers.has(id); }
    addLayer(layer: { id: string }) { this.layers.add(layer.id); }
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
  Map: mock.Map, NavigationControl: class {}, ScaleControl: class {}, setWorkerUrl: vi.fn(),
}));
vi.mock("maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url", () => ({ default: "mock-worker" }));

import { MapView } from "./MapView";

function renderMap() {
  const area = { type: "Feature", geometry: { type: "MultiPolygon", coordinates: [] } } as unknown as AreaFeature;
  const waterBody: GeoJSONFeatureCollection = { type: "FeatureCollection", features: [] };
  const { unmount } = render(<MapView
    initial={{ longitude: -1, latitude: 52, zoom: 8 }}
    activeLayers={new Set(["water-supply"])}
    hydrology={[]} waterQuality={[]} reservoirs={[]}
    area={area} waterBody={waterBody}
    onViewport={vi.fn()} onMapClick={vi.fn()} onSelectPoint={vi.fn()}
  />);
  return { area, waterBody, map: mock.Map.latest, unmount };
}

it("restores current data only after the initial and fallback styles fully load", () => {
  const { area, waterBody, map, unmount } = renderMap();
  expect(map.sources.size).toBe(0);
  act(() => { map.loaded = true; map.emit("load"); });
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
