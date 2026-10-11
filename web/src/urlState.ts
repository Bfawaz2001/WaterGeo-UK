import type { LayerId } from "./types";

export interface ExplorerState {
  longitude: number;
  latitude: number;
  zoom: number;
  layers: Set<LayerId>;
  selected: string | null;
  floodSeverity: "" | "1" | "2" | "3" | "4";
  bathingClassification: "" | "Excellent" | "Good" | "Sufficient" | "Poor" | "unclassified";
}

export const DEFAULT_STATE: ExplorerState = {
  longitude: -2.5,
  latitude: 54.5,
  zoom: 5.2,
  layers: new Set<LayerId>(["hydrology"]),
  selected: null,
  floodSeverity: "",
  bathingClassification: "",
};

const LAYERS = new Set<LayerId>([
  "hydrology",
  "rainfall",
  "water-quality",
  "flood-warnings",
  "bathing-waters",
  "reservoirs",
  "thames-discharge",
  "water-supply",
]);
const SELECTION = /^(hydrology|rainfall|water-quality|flood-warnings|bathing-waters|reservoirs|thames-discharge|water-supply|water-body):.{1,160}$/u;
const FLOOD_SEVERITIES = new Set(["1", "2", "3", "4"] as const);
const BATHING_CLASSIFICATIONS = new Set(["Excellent", "Good", "Sufficient", "Poor", "unclassified"] as const);

export function parseWaterSupplyId(value: string): number | null {
  if (!/^[0-9]+$/u.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function validSelection(value: string | null): value is string {
  return value !== null && SELECTION.test(value) &&
    (!value.startsWith("water-supply:") ||
      parseWaterSupplyId(value.slice("water-supply:".length)) !== null);
}

function finiteIn(value: string | null, minimum: number, maximum: number): number | null {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
}

export function parseExplorerState(search: string): ExplorerState {
  const params = new URLSearchParams(search);
  const longitude = finiteIn(params.get("lon"), -180, 180) ?? DEFAULT_STATE.longitude;
  const latitude = finiteIn(params.get("lat"), -90, 90) ?? DEFAULT_STATE.latitude;
  const zoom = finiteIn(params.get("z"), 3, 17) ?? DEFAULT_STATE.zoom;
  const requestedLayers = (params.get("layers") ?? "hydrology").split(",");
  const layers = new Set(
    requestedLayers.filter((layer): layer is LayerId => LAYERS.has(layer as LayerId)),
  );
  const selectedValue = params.get("selected");
  const floodSeverity = params.get("flood");
  const bathingClassification = params.get("bathing");
  return {
    longitude,
    latitude,
    zoom,
    layers: layers.size > 0 ? layers : new Set(DEFAULT_STATE.layers),
    selected: validSelection(selectedValue) ? selectedValue : null,
    floodSeverity: FLOOD_SEVERITIES.has(floodSeverity as "1")
      ? floodSeverity as ExplorerState["floodSeverity"]
      : "",
    bathingClassification: BATHING_CLASSIFICATIONS.has(bathingClassification as "Excellent")
      ? bathingClassification as ExplorerState["bathingClassification"]
      : "",
  };
}

export function explorerSearch(state: ExplorerState): string {
  const params = new URLSearchParams({
    lon: state.longitude.toFixed(5),
    lat: state.latitude.toFixed(5),
    z: state.zoom.toFixed(2),
    layers: [...state.layers].sort().join(","),
  });
  if (validSelection(state.selected)) {
    params.set("selected", state.selected);
  }
  if (state.floodSeverity) params.set("flood", state.floodSeverity);
  if (state.bathingClassification) params.set("bathing", state.bathingClassification);
  return `?${params.toString()}`;
}
