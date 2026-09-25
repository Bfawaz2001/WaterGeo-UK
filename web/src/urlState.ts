import type { LayerId } from "./types";

export interface ExplorerState {
  longitude: number;
  latitude: number;
  zoom: number;
  layers: Set<LayerId>;
  selected: string | null;
}

export const DEFAULT_STATE: ExplorerState = {
  longitude: -2.5,
  latitude: 54.5,
  zoom: 5.2,
  layers: new Set<LayerId>(["hydrology"]),
  selected: null,
};

const LAYERS = new Set<LayerId>([
  "hydrology",
  "water-quality",
  "reservoirs",
  "water-supply",
]);
const SELECTION = /^(hydrology|water-quality|reservoirs|water-supply|water-body):.{1,160}$/u;

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
  return {
    longitude,
    latitude,
    zoom,
    layers: layers.size > 0 ? layers : new Set(DEFAULT_STATE.layers),
    selected: selectedValue !== null && SELECTION.test(selectedValue) ? selectedValue : null,
  };
}

export function explorerSearch(state: ExplorerState): string {
  const params = new URLSearchParams({
    lon: state.longitude.toFixed(5),
    lat: state.latitude.toFixed(5),
    z: state.zoom.toFixed(2),
    layers: [...state.layers].sort().join(","),
  });
  if (state.selected !== null && SELECTION.test(state.selected)) {
    params.set("selected", state.selected);
  }
  return `?${params.toString()}`;
}
